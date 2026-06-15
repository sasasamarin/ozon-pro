"""
/ads/product-stats — per-SKU статистика рекламы «Оплата за клик» за вчера.

Источник — безлимитный метод Performance API get_product_sku_stats
(POST /api/client/statistics/products/sku). Метод отдаёт данные только за
сегодня/вчера, поэтому показываем ВЧЕРА (финализировано после 3:00 мск).

Live read-through (без хранения → без риска двойного счёта в ad_statistics).
Маппинг рекламного sku → товар через мост order_items.ozon_sku → product_id
(рекламный sku ≠ Product.ozon_sku — двойственность SKU Ozon). source='api'.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.deps_cabinets import get_accessible_cabinet_ids
from app.core.logging import log
from app.db.session import get_db
from app.models import OzonAccount, User
from app.services.ozon_perf_client import OzonPerfNotConfigured, OzonPerformanceClient

router = APIRouter()


class AdSkuRow(BaseModel):
    cabinet_id: str
    cabinet_name: str
    sku: str
    product_id: str | None
    product_name: str | None
    views: int
    clicks: int
    ctr: float
    avg_cpc: float
    spend: float
    orders: int
    sales: float
    drr: float


class AdSkuStatsResponse(BaseModel):
    date: str
    rows: list[AdSkuRow]
    total_spend: float
    total_sales: float
    drr_pct: float | None
    matched_to_products: int
    skipped_cabinets: list[str]
    source: str = "api"
    note: str


@router.get("/product-stats", response_model=AdSkuStatsResponse)
async def ad_product_stats(
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdSkuStatsResponse:
    """Реклама «Оплата за клик» по товарам за вчера (live из Ozon, без лимитов)."""
    # Вчера по МСК — данные за этот день уже финализированы (фиксация в 3:00 мск).
    msk_yesterday = (datetime.now(UTC) + timedelta(hours=3)).date() - timedelta(days=1)
    day = msk_yesterday.isoformat()

    accessible = await get_accessible_cabinet_ids(db, current_user)
    q = select(OzonAccount).where(
        OzonAccount.company_id == current_user.company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if accessible is not None:
        q = q.where(OzonAccount.id.in_(accessible))
    if cabinet_ids:
        q = q.where(OzonAccount.id.in_(cabinet_ids))
    accounts = (await db.execute(q)).scalars().all()

    rows: list[AdSkuRow] = []
    skipped: list[str] = []
    total_spend = 0.0
    total_sales = 0.0
    matched = 0

    for acc in accounts:
        if not acc.perf_client_id_encrypted:
            skipped.append(acc.name)
            continue

        # Мост ad_sku -> product: order_items.ozon_sku (вариантный sku) -> product_id.
        bridge_rows = (await db.execute(text("""
            SELECT DISTINCT oi.ozon_sku, oi.product_id, p.name
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            JOIN products p ON p.id = oi.product_id
            WHERE o.ozon_account_id = :acc AND oi.product_id IS NOT NULL
              AND oi.ozon_sku IS NOT NULL
        """), {"acc": str(acc.id)})).all()
        sku_map: dict[str, tuple[str, str]] = {
            str(b.ozon_sku): (str(b.product_id), b.name) for b in bridge_rows
        }

        try:
            async with OzonPerformanceClient(acc, db) as client:
                campaigns = await client.get_campaigns()
                cpc_ids = [
                    c.get("id") for c in campaigns
                    if c.get("state") == "CAMPAIGN_STATE_RUNNING"
                    and c.get("advObjectType") == "SKU"
                ]
                stats = await client.get_product_sku_stats(
                    campaign_ids=cpc_ids, date_from=day, date_to=day,
                )
        except OzonPerfNotConfigured:
            skipped.append(acc.name)
            continue
        except Exception:  # noqa: BLE001
            log.warning("ad_product_stats_cabinet_failed", account_id=str(acc.id))
            skipped.append(acc.name)
            continue

        # Агрегируем по sku (один sku может быть в нескольких кампаниях за день).
        agg: dict[str, dict] = {}
        for p in stats:
            sku = p.get("sku")
            if not sku:
                continue
            a = agg.setdefault(sku, {
                "views": 0, "clicks": 0, "spend": 0.0, "orders": 0, "sales": 0.0,
            })
            a["views"] += p["views"]
            a["clicks"] += p["clicks"]
            a["spend"] += p["expense"]
            a["orders"] += p["orders"]
            a["sales"] += p["sales"]

        for sku, a in agg.items():
            pid, pname = sku_map.get(str(sku), (None, None))
            if pid:
                matched += 1
            spend = a["spend"]
            sales = a["sales"]
            rows.append(AdSkuRow(
                cabinet_id=str(acc.id), cabinet_name=acc.name,
                sku=str(sku), product_id=pid, product_name=pname,
                views=a["views"], clicks=a["clicks"],
                ctr=round(a["clicks"] / a["views"] * 100, 2) if a["views"] else 0.0,
                avg_cpc=round(spend / a["clicks"], 2) if a["clicks"] else 0.0,
                spend=round(spend, 2), orders=a["orders"], sales=round(sales, 2),
                drr=round(spend / sales * 100, 1) if sales else 0.0,
            ))
            total_spend += spend
            total_sales += sales

    rows.sort(key=lambda r: r.spend, reverse=True)
    return AdSkuStatsResponse(
        date=day,
        rows=rows,
        total_spend=round(total_spend, 2),
        total_sales=round(total_sales, 2),
        drr_pct=round(total_spend / total_sales * 100, 2) if total_sales else None,
        matched_to_products=matched,
        skipped_cabinets=skipped,
        source="api",
        note=f"Реклама «Оплата за клик» по товарам за {day} (Performance API, "
             "только вчера/сегодня, лимиты не расходует).",
    )
