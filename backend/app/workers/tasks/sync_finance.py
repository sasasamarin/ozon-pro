"""
Синхронизация финансовых транзакций Ozon.

Endpoint: POST /v3/finance/transaction/list
Ozon ограничивает диапазон одним месяцем на запрос → разбиваем по 7-дневным
чанкам отдельными Celery-тасками.

- sync_all_transactions   — orchestrator: ищет кабинеты, строит чанки,
                             диспатчит sync_transactions_chunk через .delay()+
                             .get(), агрегирует результаты.
- sync_transactions_chunk — атомарная Celery-таск на один (account, df→dt)
                             7-дневный (или меньше) отрезок. Внутри —
                             пагинация по странице, ON CONFLICT upsert.

Идемпотентно: PK (time, ozon_transaction_id) + on_conflict_do_nothing.
Ошибка одного чанка НЕ валит весь backfill.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.core.security import decrypt_secret
from app.models import OzonAccount, OzonAccountStatus, Transaction
from app.services.ozon_client import OzonAPIError, OzonSellerClient
from app.services.transaction_classifier import buckets_from_operation
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import (
    get_active_accounts,
    get_sync_cursor,
    run_celery_async,
    save_sync_cursor,
    track_sync_log,
)


_PAGE_SIZE = 1000
_MAX_PAGES_TX = 5000  # >5000 страниц на 7-дневный чанк маловероятно
_CHUNK_DAYS = 7  # размер sub-chunk'а — безопасно укладывается в Celery soft-time-limit


# ============================================================
# ORCHESTRATOR
# ============================================================


@celery_app.task(name="app.workers.tasks.sync_finance.sync_all_transactions")
def sync_all_transactions(
    days_window: int = 3,
    date_from: str | None = None,
    account_id: str | None = None,
) -> dict:
    """Транзакции: orchestrator → sub-tasks по 7-дневным чанкам."""
    return run_celery_async(_orchestrate, days_window, date_from, account_id)


_TX_ENDPOINT = "/v3/finance/transaction/list"  # ключ в sync_state
# Rolling-окно: проводки/комиссии Ozon могут приходить задним числом.
# Особенно для возвратов — комиссия за возврат может прийти через 1-2 недели
# после фактического возврата товара. 14 дней — консервативное окно.
_TX_REPROCESS_TAIL_DAYS = 14


async def _orchestrate(
    SessionLocal: async_sessionmaker[AsyncSession],
    days_window: int,
    date_from_iso: str | None,
    account_id: str | None,
) -> dict:
    async with SessionLocal() as db:
        if account_id:
            acc = (
                await db.execute(
                    select(OzonAccount).where(
                        OzonAccount.id == uuid.UUID(account_id),
                        OzonAccount.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            accounts = [acc] if acc else []
        else:
            accounts = await get_active_accounts(db)

    date_to = datetime.now(UTC)
    if date_from_iso:
        try:
            date_from = datetime.fromisoformat(date_from_iso.replace("Z", "+00:00"))
            if date_from.tzinfo is None:
                date_from = date_from.replace(tzinfo=UTC)
        except ValueError:
            return {"error": f"invalid date_from={date_from_iso}"}
    else:
        date_from = date_to - timedelta(days=days_window)

    # Кабинеты параллельно (как в sync_orders и обновлённом sync_analytics)
    results = await asyncio.gather(*[
        _sync_account(SessionLocal, acc, date_from, date_to, override_from=bool(date_from_iso))
        for acc in accounts
    ], return_exceptions=True)

    summary = {
        "total_chunks": 0, "success": 0, "failed": 0, "skipped": 0,
        "records": 0, "by_account": {},
    }
    for acc, res in zip(accounts, results):
        if isinstance(res, Exception):
            log.exception("tx_account_crash", account=str(acc.id))
            summary["by_account"][str(acc.id)] = {"error": str(res), "chunks": 0}
            summary["failed"] += 1
            continue
        summary["total_chunks"] += res["chunks"]
        summary["success"]      += res["success"]
        summary["failed"]       += res["failed"]
        summary["skipped"]      += res["skipped"]
        summary["records"]      += res["records"]
        summary["by_account"][str(acc.id)] = res
        log.info(
            "transactions_backfill_done",
            account=str(acc.id),
            **res,
        )

    log.info("transactions_backfill_summary", **{k: v for k, v in summary.items() if k != "by_account"})
    return summary


async def _sync_account(
    SessionLocal: async_sessionmaker[AsyncSession],
    acc: OzonAccount,
    date_from: datetime, date_to: datetime,
    override_from: bool,
) -> dict:
    """Один кабинет — последовательно по чанкам, с cursor-resume."""
    # Resume from cursor с rolling-окном (если юзер не передал явный date_from)
    if not override_from:
        saved = await get_sync_cursor(
            SessionLocal, cabinet_id=acc.id, endpoint=_TX_ENDPOINT,
        )
        if saved:
            try:
                cur = datetime.fromisoformat(saved.replace("Z", "+00:00"))
                if cur.tzinfo is None: cur = cur.replace(tzinfo=UTC)
                # Rolling-окно: пересинк последних _TX_REPROCESS_TAIL_DAYS дней.
                # Комиссии возврата приходят с задержкой → надо перепроверять.
                rolling_lower = date_to - timedelta(days=_TX_REPROCESS_TAIL_DAYS)
                effective = min(cur, rolling_lower)
                if effective > date_from:
                    date_from = effective
                    log.info("tx_resume_from_cursor",
                             account=str(acc.id), cursor=saved,
                             effective=date_from.isoformat())
            except ValueError:
                pass

    chunks = _build_chunks(date_from, date_to, days=_CHUNK_DAYS)
    log.info("transactions_backfill_start",
             account=str(acc.id), account_name=acc.name,
             date_from=date_from.isoformat(), date_to=date_to.isoformat(),
             chunks=len(chunks))

    per_acc = {"chunks": len(chunks), "success": 0, "failed": 0, "skipped": 0, "records": 0}

    for (chunk_from, chunk_to) in chunks:
        df_iso = chunk_from.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        dt_iso = chunk_to.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        try:
            result = await _sync_chunk(SessionLocal, str(acc.id), df_iso, dt_iso)
        except Exception as e:
            log.exception("tx_chunk_crash", account=str(acc.id), df=df_iso)
            result = {"status": "failed", "error": str(e)[:200]}

        status = result.get("status") if isinstance(result, dict) else "failed"
        if status == "success":
            per_acc["success"] += 1
            per_acc["records"] += int(result.get("records", 0))
            # Окно покрытия: from=date_from (начало запрошенного диапазона),
            # to=chunk_to (двигается по мере успехов).
            await save_sync_cursor(
                SessionLocal, cabinet_id=acc.id, endpoint=_TX_ENDPOINT,
                cursor=chunk_to.isoformat(),
                synced_from=date_from.isoformat(),
                status="ok",
            )
        elif status == "skipped":
            per_acc["skipped"] += 1
        else:
            per_acc["failed"] += 1
            await save_sync_cursor(
                SessionLocal, cabinet_id=acc.id, endpoint=_TX_ENDPOINT,
                cursor=chunk_from.isoformat(),
                synced_from=date_from.isoformat(),
                status="error",
                error=result.get("error") if isinstance(result, dict) else None,
            )
            break  # стоп при первом фейле, следующий run возобновится
    return per_acc


def _build_chunks(date_from: datetime, date_to: datetime, days: int) -> list[tuple[datetime, datetime]]:
    """[date_from, date_to) → список интервалов по N дней."""
    chunks: list[tuple[datetime, datetime]] = []
    cur = date_from
    while cur < date_to:
        end = min(cur + timedelta(days=days), date_to)
        chunks.append((cur, end))
        cur = end
    return chunks


# ============================================================
# SUB-TASK: один чанк
# ============================================================


@celery_app.task(name="app.workers.tasks.sync_finance.sync_transactions_chunk")
def sync_transactions_chunk(account_id: str, date_from: str, date_to: str) -> dict:
    """Один атомарный чанк транзакций. Idempotent, retryable."""
    return run_celery_async(_sync_chunk, account_id, date_from, date_to)


async def _sync_chunk(
    SessionLocal: async_sessionmaker[AsyncSession],
    account_id: str,
    df_iso: str,
    dt_iso: str,
) -> dict:
    t0 = time.monotonic()
    cab_uuid = uuid.UUID(account_id)

    async with SessionLocal() as db:
        account = (
            await db.execute(select(OzonAccount).where(OzonAccount.id == cab_uuid))
        ).scalar_one_or_none()
        if not account:
            return {
                "status": "failed",
                "cabinet_id": account_id,
                "date_from": df_iso,
                "date_to": dt_iso,
                "error": "account_not_found",
            }

        records_total = 0
        try:
            async with track_sync_log(db, account.id, "sync_transactions_chunk") as stats:
                client_id = decrypt_secret(account.client_id_encrypted)
                api_key = decrypt_secret(account.api_key_encrypted)

                async with OzonSellerClient(client_id, api_key) as client:
                    page = 1
                    while True:
                        if page > _MAX_PAGES_TX:
                            log.error(
                                "tx_chunk_pagination_runaway",
                                cabinet=account_id, df=df_iso, dt=dt_iso, page=page,
                            )
                            break
                        response = await client.get_transactions(
                            date_from=df_iso, date_to=dt_iso,
                            page=page, page_size=_PAGE_SIZE,
                        )
                        result = response.get("result") or {}
                        operations = result.get("operations") or []
                        page_count = int(result.get("page_count", 1) or 1)
                        log.info(
                            "tx_chunk_page",
                            cabinet=account_id, df=df_iso, dt=dt_iso,
                            page=page, of=page_count, items=len(operations),
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
                            services_raw = op.get("services")
                            op_amount = _safe_float(op.get("amount")) or 0
                            # Разносим по бакетам через универсальный helper:
                            # services[] для posting-операций, operation_type
                            # для соло-операций (storage, реклама, эквайринг).
                            buckets = buckets_from_operation(
                                op.get("operation_type"), op_amount, services_raw,
                            )
                            rows.append({
                                "time": op_date,
                                "ozon_transaction_id": tid,
                                "ozon_account_id": cab_uuid,
                                "operation_type": op.get("operation_type", "unknown"),
                                "operation_type_name": op.get("operation_type_name"),
                                "operation_date": op_date,
                                "amount": _safe_float(op.get("amount")) or 0,
                                "accruals_for_sale": _safe_float(op.get("accruals_for_sale")),
                                "sale_commission": _safe_float(op.get("sale_commission")),
                                "description": op.get("type") or op.get("operation_type_name"),
                                "posting_number": posting.get("posting_number"),
                                "services": services_raw,
                                # Разнесённые буckets — для honest P&L breakdown
                                "delivery_to_customer": buckets["delivery_to_customer"],
                                "return_logistics":     buckets["return_logistics"],
                                "last_mile":            buckets["last_mile"],
                                "storage":              buckets["storage"],
                                "placement":            buckets["placement"],
                                "acquiring":            buckets["acquiring"],
                                "advertising":          buckets["advertising"],
                                "utilization":          buckets["utilization"],
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
                            records_total += len(rows)

                        if page >= page_count or len(operations) < _PAGE_SIZE:
                            break
                        page += 1

                # На success чанка — обновим last_sync_at, но НЕ статус (несколько чанков
                # параллельно: один может упасть, другой пройти — статус управляется orchestrator'ом)
                account.last_sync_at = datetime.now(UTC)
                account.last_sync_error = None
                account.status = OzonAccountStatus.ACTIVE.value
            await db.commit()
            dur = time.monotonic() - t0
            return {
                "status": "success",
                "cabinet_id": account_id,
                "date_from": df_iso,
                "date_to": dt_iso,
                "records": records_total,
                "duration_s": round(dur, 2),
            }
        except OzonAPIError as e:
            account.status = OzonAccountStatus.ERROR.value
            account.last_sync_error = str(e)[:500]
            await db.commit()
            log.exception(
                "tx_chunk_failed",
                cabinet=account_id, df=df_iso, dt=dt_iso, err=str(e),
            )
            return {
                "status": "failed",
                "cabinet_id": account_id,
                "date_from": df_iso,
                "date_to": dt_iso,
                "records": records_total,
                "duration_s": round(time.monotonic() - t0, 2),
                "error": str(e),
            }
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            log.exception("tx_chunk_unexpected", cabinet=account_id, df=df_iso, dt=dt_iso)
            return {
                "status": "failed",
                "cabinet_id": account_id,
                "date_from": df_iso,
                "date_to": dt_iso,
                "records": records_total,
                "duration_s": round(time.monotonic() - t0, 2),
                "error": str(e),
            }


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
