"""
Синхронизация финансовых транзакций Ozon.

Endpoint: POST /v3/finance/transaction/list
Идемпотентно: каждая транзакция уникальна по ozon_transaction_id.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.logging import log
from app.core.security import decrypt_secret
from app.db.session import AsyncSessionLocal
from app.models import OzonAccount, Transaction
from app.services.ozon_client import OzonAPIError, OzonSellerClient
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import get_active_accounts, track_sync_log


_PAGE_SIZE = 1000


@celery_app.task(name="app.workers.tasks.sync_finance.sync_all_transactions")
def sync_all_transactions(days_window: int = 3) -> dict:
    """Тянет последние `days_window` дней транзакций по всем магазинам."""
    return asyncio.run(_sync_all_transactions_async(days_window))


async def _sync_all_transactions_async(days_window: int) -> dict:
    async with AsyncSessionLocal() as db:
        accounts = await get_active_accounts(db)

    log.info("sync_transactions_started", accounts_count=len(accounts), days=days_window)
    results = await asyncio.gather(
        *[_sync_transactions_for_account(acc.id, days_window) for acc in accounts],
        return_exceptions=True,
    )
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    return {"total": len(accounts), "success": success, "failed": len(results) - success}


async def _sync_transactions_for_account(
    account_id: uuid.UUID, days_window: int
) -> dict:
    async with AsyncSessionLocal() as db:
        account = (
            await db.execute(select(OzonAccount).where(OzonAccount.id == account_id))
        ).scalar_one_or_none()
        if not account:
            return {"status": "failed", "error": "account_not_found"}

        date_to = datetime.now(UTC)
        date_from = date_to - timedelta(days=days_window)
        df = date_from.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        dt = date_to.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        try:
            async with track_sync_log(db, account.id, "sync_transactions") as stats:
                client_id = decrypt_secret(account.client_id_encrypted)
                api_key = decrypt_secret(account.api_key_encrypted)

                async with OzonSellerClient(client_id, api_key) as client:
                    page = 1
                    while True:
                        response = await client.get_transactions(
                            date_from=df,
                            date_to=dt,
                            page=page,
                            page_size=_PAGE_SIZE,
                        )
                        result = response.get("result") or {}
                        operations = result.get("operations") or []
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
                                "amount": _safe_float(op.get("amount")) or 0,
                                "accruals": _safe_float(op.get("accruals_for_sale")),
                                "description": op.get("type") or op.get("operation_type_name"),
                                "posting_number": posting.get("posting_number"),
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

                        page_count = result.get("page_count", 1)
                        if page >= page_count or len(operations) < _PAGE_SIZE:
                            break
                        page += 1

                account.last_sync_at = datetime.now(UTC)
            await db.commit()
            return {"status": "success", "rows": stats.created}
        except OzonAPIError as e:
            account.last_sync_error = str(e)[:500]
            await db.commit()
            return {"status": "failed", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            return {"status": "failed", "error": str(e)}


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
