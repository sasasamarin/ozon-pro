"""
/ads/product-stats — статистика рекламы «Оплата за клик» по товарам.

Зеркало кабинета Ozon «Продвижение → Оплата за клик → товары» (Принцип №1).
Источник — НОВЫЙ безлимитный метод Performance API
(get_product_stats → /api/client/statistics/campaign/product/json).

Live read-through: метод лимиты НЕ расходует, поэтому зовём на запрос и НЕ
храним. У него нет дневного среза (период = сводка Ozon, не атрибутируется к
конкретному дню), так что в дневную ad_statistics его не пишем — это была бы
неверная атрибуция. source='api'.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.deps_cabinets import get_accessible_cabinet_ids
from app.core.logging import log
from app.db.session import get_db
from app.models import OzonAccount, Product, User
from app.services.ozon_perf_client import OzonPerfNotConfigured, OzonPerformanceClient

router = APIRouter()


class AdProductRow(BaseModel):
    cabinet_id: str
    cabinet_name: str
    sku: str | None
    product_id: str | None
    product_name: str | None
    views: int
    clicks: int
    ctr: float
    click_price: float
    money_spent: float
    orders: int
    orders_money: float
    drr: float
    to_cart: int


class AdProductStatsResponse(BaseModel):
    rows: list[AdProductRow]
    total_spend: float
    total_orders_money: float
    drr_pct: float | None
    skipped_cabinets: list[str]
    source: str = "api"
    note: str


@router.get("/product-stats", response_model=AdProductStatsResponse)
async def ad_product_stats(
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdProductStatsResponse:
    """Per-SKU реклама «Оплата за клик» по доступным кабинетам (live из Ozon)."""
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

    rows: list[AdProductRow] = []
    skipped: list[str] = []
    total_spend = 0.0
    total_om = 0.0

    for acc in accounts:
        if not acc.perf_client_id_encrypted:
            skipped.append(acc.name)
            continue

        # карта sku -> (product_id, name): SKU из Ozon может прийти как
        # ozon_sku / fbo_sku / fbs_sku — мапим все варианты.
        prod_rows = (await db.execute(
            select(Product.id, Product.ozon_sku, Product.fbo_sku,
                   Product.fbs_sku, Product.name)
            .where(Product.ozon_account_id == acc.id, Product.deleted_at.is_(None))
        )).all()
        sku_map: dict[str, tuple[str, str]] = {}
        for pid, osku, fbo, fbs, name in prod_rows:
            for s in (osku, fbo, fbs):
                if s:
                    sku_map[str(s)] = (str(pid), name)

        try:
            async with OzonPerformanceClient(acc, db) as client:
                stats = await client.get_product_stats()
        except OzonPerfNotConfigured:
            skipped.append(acc.name)
            continue
        except Exception:  # noqa: BLE001
            log.warning("ad_product_stats_cabinet_failed", account_id=str(acc.id))
            skipped.append(acc.name)
            continue

        for p in stats:
            sku = p.get("sku")
            pid, pname = sku_map.get(str(sku), (None, p.get("title")))
            rows.append(AdProductRow(
                cabinet_id=str(acc.id), cabinet_name=acc.name,
                sku=sku, product_id=pid, product_name=pname,
                views=p["views"], clicks=p["clicks"], ctr=p["ctr"],
                click_price=p["click_price"], money_spent=p["money_spent"],
                orders=p["orders"], orders_money=p["orders_money"],
                drr=p["drr"], to_cart=p["to_cart"],
            ))
            total_spend += p["money_spent"]
            total_om += p["orders_money"]

    rows.sort(key=lambda r: r.money_spent, reverse=True)
    return AdProductStatsResponse(
        rows=rows,
        total_spend=round(total_spend, 2),
        total_orders_money=round(total_om, 2),
        drr_pct=round(total_spend / total_om * 100, 2) if total_om else None,
        skipped_cabinets=skipped,
        source="api",
        note="Зеркало кабинета Ozon «Оплата за клик → товары» (Performance API, "
             "сводка без дневного среза). Лимиты не расходует.",
    )
