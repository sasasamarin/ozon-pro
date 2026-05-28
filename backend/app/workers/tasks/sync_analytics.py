"""
Синхронизация ежедневной аналитики Ozon (метрики воронки по SKU).

Endpoint: POST /v1/analytics/data
Dimension: ["sku", "day"], метрики — стандартный набор воронки.
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
from app.models import AnalyticsDaily, OzonAccount, OzonAccountStatus
from app.services.ozon_client import OzonAPIError, OzonSellerClient
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import (
    get_active_accounts,
    load_sku_map,
    run_celery_async,
    track_sync_log,
)


_METRICS = [
    # Ozon AnalyticsGetDataRequest.Metrics: max 14 items.
    "ordered_units",
    "revenue",
    "hits_view_search",
    "hits_view_pdp",
    "hits_tocart_search",
    "hits_tocart_pdp",
    "session_view_search",
    "session_view_pdp",
    "conv_tocart_search",
    "conv_tocart_pdp",
    "delivered_units",
    "returns",
    "cancellations",
    "position_category",
    # Дропнуты: adv_view_pdp, adv_sum_all (advertising есть в sync_ad_statistics).
]


@celery_app.task(name="app.workers.tasks.sync_analytics.sync_all_analytics")
def sync_all_analytics(
    days_window: int = 3,
    date_from: str | None = None,
    account_id: str | None = None,
) -> dict:
    """Аналитика. cron → days_window=3, ручной backfill → date_from='2025-01-01'."""
    return run_celery_async(_sync_all_analytics_async, days_window, date_from, account_id)


async def _sync_all_analytics_async(
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

    log.info("sync_analytics_started", accounts_count=len(accounts), days=days_window, date_from=date_from)
    results = await asyncio.gather(
        *[_sync_analytics_for_account(SessionLocal, acc.id, days_window, date_from) for acc in accounts],
        return_exceptions=True,
    )
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    return {"total": len(accounts), "success": success, "failed": len(results) - success}


_MAX_PAGES_ANALYTICS = 2000


async def _sync_analytics_for_account(
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

        date_to = datetime.now(UTC).date()
        if date_from_iso:
            try:
                date_from = date_cls.fromisoformat(date_from_iso[:10])
            except ValueError:
                return {"status": "failed", "error": f"invalid date_from={date_from_iso}"}
        else:
            date_from = date_to - timedelta(days=days_window)

        # Ozon: «cannot get more than one year» → бьём по 365-дневным окнам.
        # Берём с запасом 350 дней.
        from datetime import timedelta as _td
        year_chunks: list[tuple[date_cls, date_cls]] = []
        cur = date_from
        while cur < date_to:
            end = min(cur + _td(days=350), date_to)
            year_chunks.append((cur, end))
            cur = end

        log.info("analytics_chunks", account=str(account_id), chunks=len(year_chunks))

        try:
            async with track_sync_log(db, account.id, "sync_analytics") as stats:
                sku_to_id = await load_sku_map(db, account.id)
                client_id = decrypt_secret(account.client_id_encrypted)
                api_key = decrypt_secret(account.api_key_encrypted)

                rows: list[dict] = []

                async with OzonSellerClient(client_id, api_key) as client:
                    for chunk_idx, (chunk_from, chunk_to) in enumerate(year_chunks, 1):
                        offset = 0
                        page = 0
                        while True:
                            page += 1
                            if page > _MAX_PAGES_ANALYTICS:
                                log.error("pagination_runaway", method="analytics", account=str(account_id), page=page)
                                break
                            response = await client.get_analytics(
                                date_from=chunk_from.isoformat(),
                                date_to=chunk_to.isoformat(),
                                dimension=["sku", "day"],
                                metrics=_METRICS,
                                limit=1000,
                                offset=offset,
                            )
                            result = response.get("result") or {}
                            data = result.get("data") or []
                            log.info(
                                "analytics_page",
                                account=str(account_id),
                                chunk=chunk_idx, of=len(year_chunks),
                                page=page, items=len(data),
                            )
                            if not data:
                                break

                        for entry in data:
                            dims = entry.get("dimensions") or []
                            sku_dim = next((d for d in dims if d.get("name") == "sku"), None)
                            day_dim = next((d for d in dims if d.get("name") == "day"), None)
                            if not sku_dim or not day_dim:
                                continue

                            try:
                                ozon_sku = int(sku_dim.get("id", 0))
                            except (TypeError, ValueError):
                                continue
                            product_id = sku_to_id.get(ozon_sku)
                            if not product_id:
                                continue

                            day_value = _parse_date(day_dim.get("id"))
                            if not day_value:
                                continue

                            metric_map = dict(zip(_METRICS, entry.get("metrics", []), strict=False))
                            rows.append({
                                "date": day_value,
                                "product_id": product_id,
                                **_metric_row(metric_map),
                            })
                            stats.processed += 1

                            # Pagination внутри year-chunk'а
                            if len(data) < 1000:
                                break
                            offset += 1000

                if rows:
                    stmt = pg_insert(AnalyticsDaily).values(rows)
                    # При повторном фетче того же дня — обновляем значения
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["date", "product_id"],
                        set_={
                            col: stmt.excluded[col]
                            for col in (
                                "ordered_units", "revenue",
                                "hits_view_search", "hits_view_pdp",
                                "hits_tocart_search", "hits_tocart_pdp",
                                "session_view_search", "session_view_pdp",
                                "conv_tocart_search", "conv_tocart_pdp",
                                "delivered_units", "returns", "cancellations",
                                "position_category",
                            )
                        },
                    )
                    await db.execute(stmt)
                    stats.updated += len(rows)

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
            return {"status": "failed", "error": str(e)}


def _parse_date(value) -> date_cls | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date_cls.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def _metric_row(m: dict) -> dict:
    """Приводит метрики из API к колонкам AnalyticsDaily."""
    return {
        "ordered_units": _to_int(m.get("ordered_units")),
        "revenue": _to_float(m.get("revenue")),
        "hits_view_search": _to_int(m.get("hits_view_search")),
        "hits_view_pdp": _to_int(m.get("hits_view_pdp")),
        "hits_tocart_search": _to_int(m.get("hits_tocart_search")),
        "hits_tocart_pdp": _to_int(m.get("hits_tocart_pdp")),
        "session_view_search": _to_int(m.get("session_view_search")),
        "session_view_pdp": _to_int(m.get("session_view_pdp")),
        "conv_tocart_search": _to_float(m.get("conv_tocart_search")),
        "conv_tocart_pdp": _to_float(m.get("conv_tocart_pdp")),
        "delivered_units": _to_int(m.get("delivered_units")),
        "returns": _to_int(m.get("returns")),
        "cancellations": _to_int(m.get("cancellations")),
        "position_category": _to_int(m.get("position_category"), nullable=True),
        # adv_view_pdp / adv_sum_all — оставляем 0 в БД (поля NOT NULL DEFAULT 0).
    }


def _to_int(value, nullable: bool = False) -> int | None:
    if value is None or value == "":
        return None if nullable else 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None if nullable else 0


def _to_float(value) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
