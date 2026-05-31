"""
Синхронизация заказов FBO + FBS.

Каждый тик: тянем `days_window` последних дней (по умолчанию 3 — incremental),
делаем upsert по posting_number, переписываем order_items набело.
Первый ручной запуск — `days_window=7`, дальше расширяем до 30.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.core.security import decrypt_secret
from app.models import Order, OrderItem, OrderType, OzonAccount, OzonAccountStatus
from app.services.ozon_client import OzonAPIError, OzonSellerClient
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import (
    get_active_accounts,
    get_sync_cursor,
    load_offer_id_map,
    load_sku_map,
    run_celery_async,
    save_sync_cursor,
    track_sync_log,
)


_FBO_PAGE_SIZE = 1000
_FBS_PAGE_SIZE = 1000
_DATE_CHUNK_DAYS = 30  # Ozon enforces MAX_OFFSET (~20 000) — стартуем offset=0 на каждом 30-дневном окне


@celery_app.task(name="app.workers.tasks.sync_orders.sync_all_orders")
def sync_all_orders(days_window: int = 3, date_from: str | None = None, account_id: str | None = None) -> dict:
    """Синхронизация заказов FBO + FBS.

    - cron: вызывает с default days_window=3 → incremental
    - manual backfill: передай date_from="2025-01-01" чтобы тянуть с указанной даты
    - phase-A прогон: account_id="<uuid>" чтобы прогнать на одном кабинете
    """
    return run_celery_async(_sync_all_orders_async, days_window, date_from, account_id)


async def _sync_all_orders_async(
    SessionLocal: async_sessionmaker[AsyncSession],
    days_window: int,
    date_from: str | None = None,
    account_id: str | None = None,
) -> dict:
    async with SessionLocal() as db:
        if account_id:
            account = (
                await db.execute(select(OzonAccount).where(OzonAccount.id == uuid.UUID(account_id), OzonAccount.deleted_at.is_(None)))
            ).scalar_one_or_none()
            accounts = [account] if account else []
        else:
            accounts = await get_active_accounts(db)

    log.info("sync_orders_started", accounts_count=len(accounts), days=days_window, date_from=date_from)
    results = await asyncio.gather(
        *[_sync_orders_for_account(SessionLocal, acc.id, days_window, date_from) for acc in accounts],
        return_exceptions=True,
    )
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    return {"total": len(accounts), "success": success, "failed": len(results) - success}


_ORDERS_ENDPOINT = "/v3/posting/fbo/list"  # ключ в sync_state
# Rolling-окно: статусы заказов (delivered/cancelled/returned) едут задним числом
# до 3 дней. Каждый run пересинкаем последние 3 дня даже если cursor свежее.
_ORDERS_REPROCESS_TAIL_DAYS = 3 (общий FBO+FBS)


async def _sync_orders_for_account(
    SessionLocal: async_sessionmaker[AsyncSession],
    account_id: uuid.UUID,
    days_window: int,
    date_from_iso: str | None = None,
) -> dict:
    async with SessionLocal() as db:
        account = (
            await db.execute(select(OzonAccount).where(OzonAccount.id == account_id))
        ).scalar_one_or_none()
        if not account:
            return {"status": "failed", "error": "account_not_found"}

        date_to = datetime.now(UTC)
        if date_from_iso:
            try:
                date_from = datetime.fromisoformat(date_from_iso.replace("Z", "+00:00"))
                if date_from.tzinfo is None:
                    date_from = date_from.replace(tzinfo=UTC)
            except ValueError:
                return {"status": "failed", "error": f"invalid date_from={date_from_iso}"}
        else:
            date_from = date_to - timedelta(days=days_window)

    # Resume from cursor (выполняем вне async-with чтобы не держать сессию)
    # Окно date_from..date_to сдвигаем вперёд если cursor свежее, но не пропускаем
    # последние 3 дня (статусы заказов ещё едут — их перепроверяем всегда).
    saved_cursor = await get_sync_cursor(
        SessionLocal, cabinet_id=account_id, endpoint=_ORDERS_ENDPOINT,
    )
    if saved_cursor and not date_from_iso:
        try:
            cursor_dt = datetime.fromisoformat(saved_cursor.replace("Z", "+00:00"))
            if cursor_dt.tzinfo is None:
                cursor_dt = cursor_dt.replace(tzinfo=UTC)
            # Rolling-окно: всегда перепроверяем последние N дней.
            recheck_from = date_to - timedelta(days=_ORDERS_REPROCESS_TAIL_DAYS)
            effective_from = min(cursor_dt, recheck_from)
            if effective_from > date_from:
                date_from = effective_from
                log.info("orders_resume_from_cursor",
                         account=str(account_id),
                         saved=saved_cursor, effective=date_from.isoformat())
        except ValueError:
            pass

    async with SessionLocal() as db:
        account = (
            await db.execute(select(OzonAccount).where(OzonAccount.id == account_id))
        ).scalar_one_or_none()
        if not account:
            return {"status": "failed", "error": "account_not_found"}

        # Бьём весь интервал на 30-дневные окна — внутри окна offset стартует
        # с 0, что обходит MAX_OFFSET_EXCEEDED у Ozon (порог ~20 000).
        date_chunks: list[tuple[datetime, datetime]] = []
        cur = date_from
        while cur < date_to:
            end = min(cur + timedelta(days=_DATE_CHUNK_DAYS), date_to)
            date_chunks.append((cur, end))
            cur = end

        log.info(
            "orders_chunks",
            account=str(account_id),
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            chunks=len(date_chunks),
        )

        try:
            async with track_sync_log(db, account.id, "sync_orders") as stats:
                sku_to_id = await load_sku_map(db, account.id)
                offer_to_id = await load_offer_id_map(db, account.id)
                client_id = decrypt_secret(account.client_id_encrypted)
                api_key = decrypt_secret(account.api_key_encrypted)

                async with OzonSellerClient(client_id, api_key) as client:
                    for chunk_idx, (chunk_from, chunk_to) in enumerate(date_chunks, 1):
                        df = chunk_from.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                        dt = chunk_to.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                        log.info(
                            "orders_chunk_start",
                            account=str(account_id),
                            chunk=chunk_idx, of=len(date_chunks),
                            df=df, dt=dt,
                        )
                        await _ingest_postings(
                            db,
                            account_id=account.id,
                            order_type=OrderType.FBO.value,
                            fetch=lambda offset, _df=df, _dt=dt: client.get_fbo_orders(
                                date_from=_df, date_to=_dt, limit=_FBO_PAGE_SIZE, offset=offset
                            ),
                            sku_to_id=sku_to_id,
                            offer_to_id=offer_to_id,
                            stats=stats,
                        )
                        await _ingest_postings(
                            db,
                            account_id=account.id,
                            order_type=OrderType.FBS.value,
                            fetch=lambda offset, _df=df, _dt=dt: client.get_fbs_orders(
                                date_from=_df, date_to=_dt, limit=_FBS_PAGE_SIZE, offset=offset
                            ),
                            sku_to_id=sku_to_id,
                            offer_to_id=offer_to_id,
                            stats=stats,
                        )

                account.last_sync_at = datetime.now(UTC)
                account.last_sync_error = None
                account.status = OzonAccountStatus.ACTIVE.value
            await db.commit()

            # Сдвигаем окно [date_from, date_to] — что покрыто этим прогоном
            await save_sync_cursor(
                SessionLocal, cabinet_id=account_id, endpoint=_ORDERS_ENDPOINT,
                cursor=date_to.isoformat(),
                synced_from=date_from.isoformat(),
                status="ok",
            )
            return {"status": "success", "rows": stats.processed}
        except OzonAPIError as e:
            account.status = OzonAccountStatus.ERROR.value
            account.last_sync_error = str(e)[:500]
            await db.commit()
            return {"status": "failed", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            return {"status": "failed", "error": str(e)}


_MAX_PAGES = 1000  # sanity-cap для всех paginate-циклов


async def _ingest_postings(
    db: AsyncSession,
    *,
    account_id: uuid.UUID,
    order_type: str,
    fetch,
    sku_to_id: dict[int, uuid.UUID],
    offer_to_id: dict[str, uuid.UUID],
    stats,
) -> None:
    """Постранично тянет список отправлений и upsert'ит каждое.

    Shape ответа отличается между endpoint'ами:
    - /v2/posting/fbo/list → {"result": [posting, ...], "has_next": bool}
    - /v3/posting/fbs/list → {"result": {"postings": [...], "has_next": bool}}
    """
    offset = 0
    page = 0
    while True:
        page += 1
        if page > _MAX_PAGES:
            log.error("pagination_runaway", method="orders", account=str(account_id), page=page)
            break
        response = await fetch(offset)
        result = response.get("result")

        if isinstance(result, dict):
            # FBS v3 shape
            postings = result.get("postings") or []
            has_next = bool(result.get("has_next", False))
        elif isinstance(result, list):
            # FBO v2 shape
            postings = result
            has_next = bool(response.get("has_next", len(postings) >= _FBO_PAGE_SIZE))
        else:
            postings = []
            has_next = False

        log.info(
            "orders_page",
            account=str(account_id),
            type=order_type,
            page=page,
            items=len(postings),
            has_next=has_next,
        )

        if not postings:
            break

        for posting in postings:
            if not isinstance(posting, dict):
                continue
            await _upsert_posting(
                db,
                account_id=account_id,
                order_type=order_type,
                posting=posting,
                sku_to_id=sku_to_id,
                offer_to_id=offer_to_id,
            )
            stats.processed += 1

        if not has_next:
            break
        offset += len(postings)


async def _upsert_posting(
    db: AsyncSession,
    *,
    account_id: uuid.UUID,
    order_type: str,
    posting: dict,
    sku_to_id: dict[int, uuid.UUID],
    offer_to_id: dict[str, uuid.UUID],
) -> None:
    posting_number = posting.get("posting_number")
    if not posting_number:
        return

    existing = await db.execute(
        select(Order).where(
            Order.ozon_account_id == account_id,
            Order.posting_number == posting_number,
        )
    )
    order = existing.scalar_one_or_none()

    analytics = posting.get("analytics_data") or {}
    financial = posting.get("financial_data") or {}

    payload = {
        "ozon_account_id": account_id,
        "order_id": posting.get("order_id"),
        "order_number": posting.get("order_number"),
        "posting_number": posting_number,
        "order_type": order_type,
        "status": posting.get("status", "unknown"),
        "substatus": posting.get("substatus"),
        "total_amount": _sum_amount(financial.get("products") or posting.get("products")),
        # commission_amount / delivery_price колонки NOT NULL DEFAULT 0 →
        # подставляем 0 если Ozon не вернул (часто бывает на awaiting_packaging).
        "commission_amount": _safe_float(
            financial.get("commission", {}).get("amount") if isinstance(financial.get("commission"), dict)
            else financial.get("commission_amount")
        ) or 0,
        "delivery_price": _safe_float(
            financial.get("posting_services", {}).get("marketplace_service_item_deliv_to_customer")
            if isinstance(financial.get("posting_services"), dict)
            else None
        ) or 0,
        "cluster_from": analytics.get("warehouse_name") or posting.get("warehouse_name"),
        "cluster_to": analytics.get("cluster") or analytics.get("delivery_type"),
        "delivery_method_name": analytics.get("delivery_method_name"),
        "region": analytics.get("region"),
        "city": analytics.get("city"),
        "order_created_at": _parse_dt(posting.get("created_at") or posting.get("in_process_at")),
        "shipment_date": _parse_dt(posting.get("shipment_date")),
        "in_process_at": _parse_dt(posting.get("in_process_at")),
        "delivering_date": _parse_dt(posting.get("delivering_date")),
        "delivered_at": _parse_dt(posting.get("delivered_at")),
        "raw_data": posting,
    }

    if order:
        for k, v in payload.items():
            setattr(order, k, v)
        await db.flush()
        await db.execute(delete(OrderItem).where(OrderItem.order_id == order.id))
    else:
        order = Order(**payload)
        db.add(order)
        await db.flush()

    for item in posting.get("products") or []:
        ozon_sku = item.get("sku") or item.get("product_id")
        offer_id = item.get("offer_id")
        # offer_id у Ozon стабильный, sku в постингах = SKU варианта склада
        # (FBO/FBS), отличается от primary ozon_sku в /v3/product/list. Поэтому
        # матчим сначала по offer_id, потом fallback на sku.
        product_id = offer_to_id.get(offer_id) if offer_id else None
        if product_id is None and ozon_sku is not None:
            product_id = sku_to_id.get(ozon_sku)
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=product_id,
                ozon_sku=ozon_sku or 0,
                offer_id=offer_id,
                name=item.get("name"),
                quantity=int(item.get("quantity", 1)),
                price=_safe_float(item.get("price")) or 0,
                total_price=_safe_float(item.get("total_price"))
                or (_safe_float(item.get("price")) or 0) * int(item.get("quantity", 1)),
                commission=_safe_float(item.get("commission_amount")) or 0,
            )
        )


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _safe_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sum_amount(items) -> float:
    if not items:
        return 0.0
    total = 0.0
    for it in items:
        price = _safe_float(it.get("price")) or 0
        qty = int(it.get("quantity", 1))
        total += price * qty
    return total
