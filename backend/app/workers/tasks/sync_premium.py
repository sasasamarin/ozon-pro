"""
Premium Plus sync-таски:
- sync_product_queries_daily: /v1/analytics/product-queries за КАЖДЫЙ день.
- sync_realization_daily: /v1/finance/realization/by-day за последние 32 дня.

Throttle: ≤ 1 RPS (sleep 1.5s между запросами).
"""
from __future__ import annotations

import asyncio
from datetime import UTC, date as date_cls, datetime, timedelta

from celery import shared_task
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.core.security import decrypt_secret
from app.models import (
    OzonAccount, ProductQueriesDaily, RealizationDaily,
)
from app.services.ozon_client import OzonAPIError, OzonSellerClient
from app.services.parsers.ozon_realization_aggregator import aggregate_realization_rows
from app.workers.tasks._helpers import (
    get_active_accounts, load_extended_sku_map, run_celery_async,
)


_PAGE_SLEEP_S = 1.5


@shared_task(name="sync_product_queries_daily", bind=True)
def sync_product_queries_daily(self, days_back: int = 7) -> dict:
    return run_celery_async(_sync_product_queries_async, days_back=days_back)


async def _sync_product_queries_async(
    SessionLocal: async_sessionmaker[AsyncSession],
    days_back: int = 7,
) -> dict:
    today = datetime.now(UTC).date()
    days = [today - timedelta(days=i) for i in range(1, days_back + 1)]

    async with SessionLocal() as db:
        accounts = await get_active_accounts(db)

    total_rows = 0
    for acc in accounts:
        async with SessionLocal() as db:
            sku_to_id = await load_extended_sku_map(db, acc.id)
        cid = decrypt_secret(acc.client_id_encrypted)
        apk = decrypt_secret(acc.api_key_encrypted)
        async with OzonSellerClient(cid, apk) as client:
            for d in days:
                df = f"{d.isoformat()}T00:00:00Z"
                dt = f"{d.isoformat()}T23:59:59Z"
                try:
                    r = await client._request(
                        "POST", "/v1/analytics/product-queries",
                        json={"date_from": df, "date_to": dt, "page_size": 1000},
                    )
                    items = r.get("items") or []
                except OzonAPIError as e:
                    log.warning("product_queries_fail", account=str(acc.id),
                                date=d.isoformat(), err=str(e)[:120])
                    await asyncio.sleep(_PAGE_SLEEP_S)
                    continue

                bulk = []
                for it in items:
                    sku = it.get("sku")
                    if not sku:
                        continue
                    bulk.append({
                        "cabinet_id": acc.id,
                        "sku": int(sku),
                        "date": d,
                        "product_id": sku_to_id.get(int(sku)),
                        "offer_id": it.get("offer_id"),
                        "unique_search_users": _to_int(it.get("unique_search_users")),
                        "unique_view_users": _to_int(it.get("unique_view_users")),
                        "position": _to_num(it.get("position")),
                        "view_conversion": _to_num(it.get("view_conversion")),
                        "gmv": _to_num(it.get("gmv")),
                        "category": (it.get("category") or "")[:50] or None,
                    })
                if bulk:
                    async with SessionLocal() as db:
                        stmt = pg_insert(ProductQueriesDaily).values(bulk)
                        stmt = stmt.on_conflict_do_update(
                            constraint="pk_product_queries_daily",
                            set_={c: stmt.excluded[c] for c in (
                                "product_id", "offer_id", "unique_search_users",
                                "unique_view_users", "position", "view_conversion",
                                "gmv", "category",
                            )},
                        )
                        await db.execute(stmt)
                        await db.commit()
                    total_rows += len(bulk)
                log.info("product_queries_synced", account=str(acc.id),
                         date=d.isoformat(), items=len(bulk))
                await asyncio.sleep(_PAGE_SLEEP_S)

    return {"accounts": len(accounts), "days": days_back, "rows": total_rows}


@shared_task(name="sync_realization_daily", bind=True)
def sync_realization_daily(self, days_back: int = 32) -> dict:
    return run_celery_async(_sync_realization_daily_async, days_back=days_back)


async def _sync_realization_daily_async(
    SessionLocal: async_sessionmaker[AsyncSession],
    days_back: int = 32,
) -> dict:
    today = datetime.now(UTC).date()
    # Последние N дней, исключая сегодня (отчёт за сегодня ещё не закрыт)
    days = [today - timedelta(days=i) for i in range(1, days_back + 1)]

    async with SessionLocal() as db:
        accounts = await get_active_accounts(db)

    total_rows = 0
    for acc in accounts:
        async with SessionLocal() as db:
            sku_to_id = await load_extended_sku_map(db, acc.id)
        cid = decrypt_secret(acc.client_id_encrypted)
        apk = decrypt_secret(acc.api_key_encrypted)
        async with OzonSellerClient(cid, apk) as client:
            for d in days:
                try:
                    r = await client._request(
                        "POST", "/v1/finance/realization/by-day",
                        json={"day": d.day, "month": d.month, "year": d.year},
                    )
                    rows = r.get("rows") or (r.get("result") or {}).get("rows") or []
                except OzonAPIError as e:
                    log.warning("realization_daily_fail", account=str(acc.id),
                                date=d.isoformat(), err=str(e)[:120])
                    await asyncio.sleep(_PAGE_SLEEP_S)
                    continue

                per_sku = aggregate_realization_rows(rows)
                bulk = []
                for sku, agg in per_sku.items():
                    if agg.qty_sold <= 0:
                        continue
                    bulk.append({
                        "cabinet_id": acc.id,
                        "sku": sku,
                        "day": d,
                        "product_id": sku_to_id.get(sku),
                        "offer_id": agg.offer_id,
                        "qty_sold": agg.qty_sold,
                        "qty_returned": agg.qty_returned,
                        "weighted_cp": round(agg.weighted_cp, 2) if agg.weighted_cp else None,
                        "weighted_sp": round(agg.weighted_sp, 2) if agg.weighted_sp else None,
                        "sum_bonus": round(agg.sum_bonus, 2),
                        "sum_fee": round(agg.sum_fee, 2),
                        "rows_aggregated": agg.rows,
                    })
                if bulk:
                    async with SessionLocal() as db:
                        stmt = pg_insert(RealizationDaily).values(bulk)
                        stmt = stmt.on_conflict_do_update(
                            constraint="pk_realization_daily",
                            set_={c: stmt.excluded[c] for c in (
                                "product_id", "offer_id", "qty_sold", "qty_returned",
                                "weighted_cp", "weighted_sp", "sum_bonus", "sum_fee",
                                "rows_aggregated",
                            )},
                        )
                        await db.execute(stmt)
                        await db.commit()
                    total_rows += len(bulk)
                log.info("realization_daily_synced", account=str(acc.id),
                         date=d.isoformat(), items=len(bulk))
                await asyncio.sleep(_PAGE_SLEEP_S)

    return {"accounts": len(accounts), "days": days_back, "rows": total_rows}


def _to_int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(str(v)))
    except (TypeError, ValueError):
        return None


def _to_num(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
