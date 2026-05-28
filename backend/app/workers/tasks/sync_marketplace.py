"""
Синхронизация возвратов, отмен, реализации (Phase 2 → Phase A).

- sync_all_returns        — /v3/returns/list, idempotent по (account, ozon_return_id)
- sync_all_cancellations  — отменённые заказы FBO+FBS из существующих
                            posting endpoints, фильтр status=cancelled
- sync_all_realization    — /v2/finance/realization помесячно
                            (требует premium_plus / premium_pro)
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date as date_cls, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.core.security import decrypt_secret
from app.models import (
    Cancellation,
    OrderType,
    OzonAccount,
    OzonAccountStatus,
    OzonPremiumTier,
    RealizationLine,
    Return,
)
from app.services.ozon_client import OzonAPIError, OzonSellerClient
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import (
    get_active_accounts,
    load_sku_map,
    run_celery_async,
    tier_at_least,
    track_sync_log,
)


_PAGE_SIZE_RETURNS = 500
_PAGE_SIZE_POSTINGS = 1000
_MAX_PAGES = 1000


# ============================================================
# RETURNS
# ============================================================


@celery_app.task(name="app.workers.tasks.sync_marketplace.sync_all_returns")
def sync_all_returns(
    days_window: int = 30,
    date_from: str | None = None,
    account_id: str | None = None,
) -> dict:
    return run_celery_async(_sync_all_returns_async, days_window, date_from, account_id)


async def _sync_all_returns_async(
    SessionLocal: async_sessionmaker[AsyncSession],
    days_window: int,
    date_from: str | None,
    account_id: str | None,
) -> dict:
    async with SessionLocal() as db:
        accounts = await _pick_accounts(db, account_id)
    log.info("sync_returns_started", count=len(accounts), date_from=date_from, days=days_window)
    results = await asyncio.gather(
        *[_sync_returns_for_account(SessionLocal, a.id, days_window, date_from) for a in accounts],
        return_exceptions=True,
    )
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    return {"total": len(accounts), "success": success, "failed": len(results) - success}


async def _sync_returns_for_account(
    SessionLocal: async_sessionmaker[AsyncSession],
    account_id: uuid.UUID,
    days_window: int,
    date_from_iso: str | None,
) -> dict:
    async with SessionLocal() as db:
        account = await _load_account(db, account_id)
        if not account:
            return {"status": "failed", "error": "account_not_found"}

        date_to = datetime.now(UTC)
        date_from = _parse_dt(date_from_iso) or (date_to - timedelta(days=days_window))
        df = date_from.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        dt = date_to.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        try:
            async with track_sync_log(db, account.id, "sync_returns") as stats:
                sku_to_id = await load_sku_map(db, account.id)
                client_id = decrypt_secret(account.client_id_encrypted)
                api_key = decrypt_secret(account.api_key_encrypted)
                async with OzonSellerClient(client_id, api_key) as client:
                    # Возвраты тянем из двух endpoint'ов: FBO + FBS отдельно.
                    for kind, fetcher in (
                        ("fbo", client.get_fbo_returns),
                        ("fbs", client.get_fbs_returns),
                    ):
                        offset = 0
                        page = 0
                        while True:
                            page += 1
                            if page > _MAX_PAGES:
                                log.error("pagination_runaway", method=f"returns_{kind}", account=str(account_id))
                                break
                            response = await fetcher(offset=offset, limit=_PAGE_SIZE_RETURNS)
                            returns = (
                                response.get("returns")
                                or response.get("result", {}).get("returns")
                                or []
                            )
                            log.info("returns_page", account=str(account_id), kind=kind, page=page, items=len(returns))
                            if not returns:
                                break
                            for r in returns:
                                if not isinstance(r, dict):
                                    continue
                                await _upsert_return(db, account_id=account.id, raw=r, sku_to_id=sku_to_id)
                                stats.processed += 1
                            if len(returns) < _PAGE_SIZE_RETURNS:
                                break
                            offset += len(returns)

                account.last_sync_at = datetime.now(UTC)
                account.last_sync_error = None
                account.status = OzonAccountStatus.ACTIVE.value
            await db.commit()
            return {"status": "success", "rows": stats.processed}
        except OzonAPIError as e:
            account.status = OzonAccountStatus.ERROR.value
            account.last_sync_error = str(e)[:500]
            await db.commit()
            return {"status": "failed", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            log.exception("sync_failed_unexpected", account_id=str(account_id))
            return {"status": "failed", "error": str(e)}


async def _upsert_return(
    db: AsyncSession, *, account_id: uuid.UUID, raw: dict, sku_to_id: dict[int, uuid.UUID]
) -> None:
    return_id = raw.get("id") or raw.get("return_id")
    if return_id is None:
        return

    sku = raw.get("sku") or raw.get("product_id")
    payload = {
        "ozon_account_id": account_id,
        "ozon_return_id": int(return_id),
        "posting_number": raw.get("posting_number"),
        "ozon_sku": int(sku) if sku else None,
        "product_id": sku_to_id.get(int(sku)) if sku else None,
        "return_type": raw.get("return_type"),
        "return_reason": raw.get("return_reason_name") or raw.get("reason"),
        "return_amount": _safe_float(raw.get("price") or raw.get("return_amount")),
        "quantity": int(raw.get("quantity", 1)),
        "status": raw.get("status"),
        "return_date": _parse_dt(raw.get("logistic_return_date") or raw.get("return_date")),
        "accepted_from_customer_at": _parse_dt(raw.get("accepted_from_customer_at")),
        "returned_to_seller_at": _parse_dt(raw.get("returned_to_seller_at")),
        "moved_to_warehouse_at": _parse_dt(raw.get("moved_to_warehouse_at")),
        "raw_data": raw,
    }
    stmt = pg_insert(Return).values(payload)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_returns_account_return",
        set_={k: payload[k] for k in payload if k not in ("ozon_account_id", "ozon_return_id")},
    )
    await db.execute(stmt)


# ============================================================
# CANCELLATIONS — фильтр cancelled из FBO+FBS
# ============================================================


@celery_app.task(name="app.workers.tasks.sync_marketplace.sync_all_cancellations")
def sync_all_cancellations(
    days_window: int = 30,
    date_from: str | None = None,
    account_id: str | None = None,
) -> dict:
    return run_celery_async(_sync_all_cancellations_async, days_window, date_from, account_id)


async def _sync_all_cancellations_async(
    SessionLocal: async_sessionmaker[AsyncSession],
    days_window: int,
    date_from: str | None,
    account_id: str | None,
) -> dict:
    async with SessionLocal() as db:
        accounts = await _pick_accounts(db, account_id)
    log.info("sync_cancellations_started", count=len(accounts), days=days_window, date_from=date_from)
    results = await asyncio.gather(
        *[_sync_cancellations_for_account(SessionLocal, a.id, days_window, date_from) for a in accounts],
        return_exceptions=True,
    )
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    return {"total": len(accounts), "success": success, "failed": len(results) - success}


async def _sync_cancellations_for_account(
    SessionLocal, account_id: uuid.UUID, days_window: int, date_from_iso: str | None
) -> dict:
    async with SessionLocal() as db:
        account = await _load_account(db, account_id)
        if not account:
            return {"status": "failed", "error": "account_not_found"}

        date_to = datetime.now(UTC)
        date_from = _parse_dt(date_from_iso) or (date_to - timedelta(days=days_window))

        # Бьём интервал на 30-дневные окна, чтобы избежать MAX_OFFSET_EXCEEDED.
        date_chunks: list[tuple[datetime, datetime]] = []
        cur = date_from
        while cur < date_to:
            end = min(cur + timedelta(days=30), date_to)
            date_chunks.append((cur, end))
            cur = end

        log.info("cancellations_chunks", account=str(account_id), chunks=len(date_chunks))

        try:
            async with track_sync_log(db, account.id, "sync_cancellations") as stats:
                client_id = decrypt_secret(account.client_id_encrypted)
                api_key = decrypt_secret(account.api_key_encrypted)
                async with OzonSellerClient(client_id, api_key) as client:
                    for chunk_idx, (chunk_from, chunk_to) in enumerate(date_chunks, 1):
                        df = chunk_from.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                        dt = chunk_to.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                        for label, fetch in (
                            (OrderType.FBO.value, lambda offset, _df=df, _dt=dt: client.get_fbo_orders(
                                date_from=_df, date_to=_dt, limit=_PAGE_SIZE_POSTINGS, offset=offset
                            )),
                            (OrderType.FBS.value, lambda offset, _df=df, _dt=dt: client.get_fbs_orders(
                                date_from=_df, date_to=_dt, limit=_PAGE_SIZE_POSTINGS, offset=offset
                            )),
                        ):
                            offset = 0
                            page = 0
                            while True:
                                page += 1
                                if page > _MAX_PAGES:
                                    log.error("pagination_runaway", method="cancellations", account=str(account_id))
                                    break
                                response = await fetch(offset)
                                result = response.get("result")
                                if isinstance(result, dict):
                                    postings = result.get("postings") or []
                                    has_next = bool(result.get("has_next", False))
                                elif isinstance(result, list):
                                    postings = result
                                    has_next = bool(response.get("has_next", len(postings) >= _PAGE_SIZE_POSTINGS))
                                else:
                                    postings, has_next = [], False
                                log.info(
                                    "cancellations_page",
                                    account=str(account_id), type=label,
                                    chunk=chunk_idx, of=len(date_chunks),
                                    page=page, items=len(postings),
                                )
                                if not postings:
                                    break
                                for p in postings:
                                    if not isinstance(p, dict):
                                        continue
                                    if str(p.get("status", "")).lower() != "cancelled":
                                        continue
                                    await _upsert_cancellation(db, account_id=account.id, raw=p, order_type=label)
                                    stats.processed += 1
                                if not has_next:
                                    break
                                offset += len(postings)

                account.last_sync_at = datetime.now(UTC)
                account.last_sync_error = None
                account.status = OzonAccountStatus.ACTIVE.value
            await db.commit()
            return {"status": "success", "rows": stats.processed}
        except OzonAPIError as e:
            account.status = OzonAccountStatus.ERROR.value
            account.last_sync_error = str(e)[:500]
            await db.commit()
            return {"status": "failed", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            log.exception("sync_failed_unexpected", account_id=str(account_id))
            return {"status": "failed", "error": str(e)}


async def _upsert_cancellation(db: AsyncSession, *, account_id: uuid.UUID, raw: dict, order_type: str) -> None:
    posting_number = raw.get("posting_number")
    if not posting_number:
        return
    cancellation = raw.get("cancellation") or {}
    products = raw.get("products") or []
    first_product = products[0] if products else {}

    payload = {
        "ozon_account_id": account_id,
        "posting_number": posting_number,
        "ozon_sku": (
            int(first_product.get("sku")) if first_product.get("sku") else (
                int(first_product.get("product_id")) if first_product.get("product_id") else None
            )
        ),
        "quantity": int(first_product.get("quantity") or 1),
        "cancel_reason_id": cancellation.get("cancel_reason_id") or raw.get("cancel_reason_id"),
        "cancel_reason_text": cancellation.get("cancel_reason") or raw.get("cancel_reason"),
        "cancelled_at": _parse_dt(cancellation.get("cancelled_at") or raw.get("cancelled_at")),
        "initiator": cancellation.get("cancellation_initiator") or raw.get("cancellation_initiator"),
        "raw_data": raw,
    }
    # Идемпотентность по posting_number в рамках кабинета.
    existing = await db.execute(
        select(Cancellation).where(
            Cancellation.ozon_account_id == account_id,
            Cancellation.posting_number == posting_number,
        )
    )
    row = existing.scalar_one_or_none()
    if row:
        for k, v in payload.items():
            setattr(row, k, v)
    else:
        db.add(Cancellation(**payload))


# ============================================================
# REALIZATION — помесячно
# ============================================================


@celery_app.task(name="app.workers.tasks.sync_marketplace.sync_all_realization")
def sync_all_realization(
    date_from: str | None = None,
    account_id: str | None = None,
) -> dict:
    """Отчёт о реализации по месяцам. По умолчанию — последний завершённый месяц.

    Premium guard: только premium_plus / premium_pro.
    """
    return run_celery_async(_sync_all_realization_async, date_from, account_id)


async def _sync_all_realization_async(
    SessionLocal: async_sessionmaker[AsyncSession],
    date_from: str | None,
    account_id: str | None,
) -> dict:
    async with SessionLocal() as db:
        accounts = await _pick_accounts(db, account_id)
    eligible = [a for a in accounts if tier_at_least(a, OzonPremiumTier.PREMIUM_PLUS, OzonPremiumTier.PREMIUM_PRO)]
    log.info("sync_realization_started", total=len(accounts), eligible=len(eligible))
    results = await asyncio.gather(
        *[_sync_realization_for_account(SessionLocal, a.id, date_from) for a in eligible],
        return_exceptions=True,
    )
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    return {"total": len(eligible), "skipped_tier": len(accounts) - len(eligible), "success": success, "failed": len(results) - success}


async def _sync_realization_for_account(
    SessionLocal, account_id: uuid.UUID, date_from_iso: str | None
) -> dict:
    async with SessionLocal() as db:
        account = await _load_account(db, account_id)
        if not account:
            return {"status": "failed", "error": "account_not_found"}

        # Определяем список месяцев: от date_from (или прошлого месяца) до сейчас.
        today = date_cls.today()
        if date_from_iso:
            try:
                start = date_cls.fromisoformat(date_from_iso[:10])
            except ValueError:
                return {"status": "failed", "error": f"invalid date_from={date_from_iso}"}
        else:
            # Если без параметра — берём прошлый завершённый месяц
            prev_month = today.replace(day=1) - timedelta(days=1)
            start = prev_month.replace(day=1)

        months: list[tuple[int, int]] = []
        cur = date_cls(start.year, start.month, 1)
        last = date_cls(today.year, today.month, 1)
        while cur <= last:
            months.append((cur.year, cur.month))
            # next month
            if cur.month == 12:
                cur = date_cls(cur.year + 1, 1, 1)
            else:
                cur = date_cls(cur.year, cur.month + 1, 1)

        try:
            async with track_sync_log(db, account.id, "sync_realization") as stats:
                client_id = decrypt_secret(account.client_id_encrypted)
                api_key = decrypt_secret(account.api_key_encrypted)
                sku_to_id = await load_sku_map(db, account.id)

                async with OzonSellerClient(client_id, api_key) as client:
                    for (year, month) in months:
                        try:
                            response = await client.get_realization(month=month, year=year)
                        except OzonAPIError as e:
                            # 404 «Report was not found» — норм для месяцев без отчёта (текущий незавершённый)
                            log.info("realization_no_report", year=year, month=month, err=str(e)[:120])
                            continue
                        result = response.get("result") or {}
                        rows = result.get("rows") or []
                        log.info("realization_month", account=str(account_id), year=year, month=month, rows=len(rows))
                        if not rows:
                            continue

                        # Период месяца
                        period_from = date_cls(year, month, 1)
                        if month == 12:
                            period_to = date_cls(year + 1, 1, 1) - timedelta(days=1)
                        else:
                            period_to = date_cls(year, month + 1, 1) - timedelta(days=1)

                        bulk = []
                        for r in rows:
                            sku = r.get("sku") or r.get("product_id")
                            if not sku:
                                continue
                            bulk.append({
                                "ozon_account_id": account_id,
                                "period_from": period_from,
                                "period_to": period_to,
                                "ozon_sku": int(sku),
                                "product_id": sku_to_id.get(int(sku)),
                                "offer_id": r.get("offer_id"),
                                "name": r.get("name"),
                                "qty_sold": int(r.get("sale_qty", 0) or 0),
                                "qty_returned": int(r.get("return_qty", 0) or 0),
                                "revenue": _safe_float(r.get("price_per_instance")) or 0,
                                "commission_amount": _safe_float((r.get("delivery_commission") or {}).get("commission_percent")) or 0,
                                "delivery_amount": _safe_float(r.get("delivery_per_unit_amount")) or 0,
                                "refund_amount": _safe_float(r.get("return_per_unit_amount")) or 0,
                                "raw_data": r,
                            })
                            stats.processed += 1

                        if bulk:
                            stmt = pg_insert(RealizationLine).values(bulk)
                            stmt = stmt.on_conflict_do_update(
                                constraint="uq_realization_account_period_sku",
                                set_={c: stmt.excluded[c] for c in (
                                    "offer_id", "name", "qty_sold", "qty_returned",
                                    "revenue", "commission_amount", "delivery_amount", "refund_amount", "raw_data",
                                )},
                            )
                            await db.execute(stmt)
                            stats.updated += len(bulk)

                account.last_sync_at = datetime.now(UTC)
                account.last_sync_error = None
                account.status = OzonAccountStatus.ACTIVE.value
            await db.commit()
            return {"status": "success", "months": len(months), "rows": stats.processed}
        except OzonAPIError as e:
            account.status = OzonAccountStatus.ERROR.value
            account.last_sync_error = str(e)[:500]
            await db.commit()
            return {"status": "failed", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            log.exception("sync_failed_unexpected", account_id=str(account_id))
            return {"status": "failed", "error": str(e)}


# ============================================================
# Хелперы
# ============================================================


async def _pick_accounts(db: AsyncSession, account_id: str | None) -> list[OzonAccount]:
    if account_id:
        acc = (
            await db.execute(
                select(OzonAccount).where(
                    OzonAccount.id == uuid.UUID(account_id),
                    OzonAccount.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        return [acc] if acc else []
    return await get_active_accounts(db)


async def _load_account(db: AsyncSession, account_id: uuid.UUID) -> OzonAccount | None:
    return (
        await db.execute(select(OzonAccount).where(OzonAccount.id == account_id))
    ).scalar_one_or_none()


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _safe_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
