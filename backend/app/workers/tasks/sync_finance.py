"""
Синхронизация финансовых транзакций Ozon.

Endpoint: POST /v3/finance/transaction/list
Идемпотентно: каждая транзакция уникальна по (time, ozon_transaction_id).

NB: user_id и поля разнесённых удержаний (delivery_to_customer, …, compensation)
пока не заполняются — Phase 2 миграция сделала их nullable / с server_default=0.
Будут заполнены в отдельной задаче после того как user-mapping станет
устойчивым (один Company → много User'ов).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.core.security import decrypt_secret
from app.models import OzonAccount, OzonAccountStatus, Transaction
from app.services.ozon_client import OzonAPIError, OzonSellerClient
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import (
    get_active_accounts,
    run_celery_async,
    track_sync_log,
)


_PAGE_SIZE = 1000


@celery_app.task(name="app.workers.tasks.sync_finance.sync_all_transactions")
def sync_all_transactions(
    days_window: int = 3,
    date_from: str | None = None,
    account_id: str | None = None,
) -> dict:
    """Транзакции Ozon. cron → days_window=3, ручной backfill → date_from."""
    return run_celery_async(_sync_all_transactions_async, days_window, date_from, account_id)


async def _sync_all_transactions_async(
    SessionLocal: async_sessionmaker[AsyncSession],
    days_window: int,
    date_from: str | None = None,
    account_id: str | None = None,
) -> dict:
    async with SessionLocal() as db:
        if account_id:
            acc = (
                await db.execute(
                    select(OzonAccount).where(OzonAccount.id == uuid.UUID(account_id), OzonAccount.deleted_at.is_(None))
                )
            ).scalar_one_or_none()
            accounts = [acc] if acc else []
        else:
            accounts = await get_active_accounts(db)

    log.info("sync_transactions_started", accounts_count=len(accounts), days=days_window, date_from=date_from)
    results = await asyncio.gather(
        *[_sync_transactions_for_account(SessionLocal, acc.id, days_window, date_from) for acc in accounts],
        return_exceptions=True,
    )
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    return {"total": len(accounts), "success": success, "failed": len(results) - success}


_MAX_PAGES_TX = 5000  # >5000 страниц транзакций маловероятно даже за 5 лет


async def _sync_transactions_for_account(
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
        df = date_from.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        dt = date_to.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        try:
            async with track_sync_log(db, account.id, "sync_transactions") as stats:
                client_id = decrypt_secret(account.client_id_encrypted)
                api_key = decrypt_secret(account.api_key_encrypted)

                # Ozon ограничивает /v3/finance/transaction/list одним месяцем за запрос.
                # Бьём окно (date_from → date_to) на месячные слайсы.
                chunks = _month_chunks(date_from, date_to)
                log.info("transactions_chunks", account=str(account_id), chunks=len(chunks))

                async with OzonSellerClient(client_id, api_key) as client:
                    for chunk_idx, (cdf, cdt) in enumerate(chunks, 1):
                        cdf_s = cdf.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                        cdt_s = cdt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                        page = 1
                        while True:
                            if page > _MAX_PAGES_TX:
                                log.error("pagination_runaway", method="transactions", account=str(account_id), page=page)
                                break
                            response = await client.get_transactions(
                                date_from=cdf_s,
                                date_to=cdt_s,
                                page=page,
                                page_size=_PAGE_SIZE,
                            )
                            result = response.get("result") or {}
                            operations = result.get("operations") or []
                            page_count = result.get("page_count", 1)
                            log.info(
                                "transactions_page",
                                account=str(account_id),
                                chunk=chunk_idx,
                                of_chunks=len(chunks),
                                page=page,
                                of=page_count,
                                items=len(operations),
                            )
                            if not operations:
                                break

                        rows = []
                        for op in operations:
                            tid = str(op.get("operation_id") or "")
                            if not tid:
                                continue
                            op_date = _parse_dt(op.get("operation_date"))
                            if not op_date:
                                continue
                            posting = op.get("posting") or {}
                            rows.append({
                                "time": op_date,
                                "ozon_transaction_id": tid,
                                "ozon_account_id": account_id,
                                "operation_type": op.get("operation_type", "unknown"),
                                "operation_type_name": op.get("operation_type_name"),
                                "operation_date": op_date,
                                "amount": _safe_float(op.get("amount")) or 0,
                                "accruals_for_sale": _safe_float(op.get("accruals_for_sale")),
                                "sale_commission": _safe_float(op.get("sale_commission")),
                                "description": op.get("type") or op.get("operation_type_name"),
                                "posting_number": posting.get("posting_number"),
                                "services": op.get("services"),
                                "raw_data": op,
                            })
                            stats.processed += 1

                        if rows:
                            stmt = pg_insert(Transaction).values(rows)
                            stmt = stmt.on_conflict_do_nothing(
                                index_elements=["time", "ozon_transaction_id"]
                            )
                            await db.execute(stmt)
                            stats.created += len(rows)

                            if page >= page_count or len(operations) < _PAGE_SIZE:
                                break
                            page += 1

                account.last_sync_at = datetime.now(UTC)
                account.last_sync_error = None
                account.status = OzonAccountStatus.ACTIVE.value
            await db.commit()
            return {"status": "success", "rows": stats.created}
        except OzonAPIError as e:
            account.status = OzonAccountStatus.ERROR.value
            account.last_sync_error = str(e)[:500]
            await db.commit()
            return {"status": "failed", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            return {"status": "failed", "error": str(e)}


def _month_chunks(date_from: datetime, date_to: datetime) -> list[tuple[datetime, datetime]]:
    """Разбивает интервал на месячные слайсы (Ozon ограничивает 1 месяц на запрос)."""
    chunks: list[tuple[datetime, datetime]] = []
    cur = date_from
    while cur < date_to:
        # Конец чанка — конец текущего месяца, но не дальше date_to
        if cur.month == 12:
            next_month = cur.replace(year=cur.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month = cur.replace(month=cur.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        chunk_end = min(next_month, date_to)
        chunks.append((cur, chunk_end))
        cur = chunk_end
    return chunks


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
