"""
/ads/campaign-stats — статистика рекламы «Оплата за клик» по кампаниям.

Зеркало кабинета Ozon «Продвижение → Оплата за клик» (Принцип №1). Источник —
безлимитный метод Performance API get_campaign_stats
(GET /api/client/statistics/campaign/product/json — несмотря на "product" в
пути, строки = КАМПАНИИ, подтверждено живым вызовом 2026-06-15).

Live read-through: метод лимиты НЕ расходует, поэтому зовём на запрос и НЕ
храним (нет дневного среза, период = сводка Ozon). source='api'.

Примечание: per-SKU ДРР этот метод не отдаёт — для статистики по товарам нужен
отдельный endpoint Ozon (путь пока не подтверждён из-за геоблока документации).
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
from app.models import OzonAccount, User
from app.services.ozon_perf_client import OzonPerfNotConfigured, OzonPerformanceClient

router = APIRouter()


class AdCampaignRow(BaseModel):
    cabinet_id: str
    cabinet_name: str
    ozon_campaign_id: str | None
    title: str | None
    status: str | None
    placement: str | None
    views: int
    clicks: int
    ctr: float
    click_price: float
    money_spent: float
    orders: int
    orders_money: float
    drr: float
    to_cart: int


class AdCampaignStatsResponse(BaseModel):
    rows: list[AdCampaignRow]
    total_spend: float
    total_orders_money: float
    drr_pct: float | None
    skipped_cabinets: list[str]
    source: str = "api"
    note: str


@router.get("/campaign-stats", response_model=AdCampaignStatsResponse)
async def ad_campaign_stats(
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    active_only: bool = Query(False, description="только не-archived кампании"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdCampaignStatsResponse:
    """Реклама «Оплата за клик» по кампаниям (live из Ozon, без расхода лимитов)."""
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

    rows: list[AdCampaignRow] = []
    skipped: list[str] = []
    total_spend = 0.0
    total_om = 0.0

    for acc in accounts:
        if not acc.perf_client_id_encrypted:
            skipped.append(acc.name)
            continue
        try:
            async with OzonPerformanceClient(acc, db) as client:
                stats = await client.get_campaign_stats()
        except OzonPerfNotConfigured:
            skipped.append(acc.name)
            continue
        except Exception:  # noqa: BLE001
            log.warning("ad_campaign_stats_cabinet_failed", account_id=str(acc.id))
            skipped.append(acc.name)
            continue

        for c in stats:
            if active_only and (c.get("status") or "").lower() == "archived":
                continue
            rows.append(AdCampaignRow(
                cabinet_id=str(acc.id), cabinet_name=acc.name,
                ozon_campaign_id=c.get("ozon_campaign_id"), title=c.get("title"),
                status=c.get("status"), placement=c.get("placement"),
                views=c["views"], clicks=c["clicks"], ctr=c["ctr"],
                click_price=c["click_price"], money_spent=c["money_spent"],
                orders=c["orders"], orders_money=c["orders_money"],
                drr=c["drr"], to_cart=c["to_cart"],
            ))
            total_spend += c["money_spent"]
            total_om += c["orders_money"]

    rows.sort(key=lambda r: r.money_spent, reverse=True)
    return AdCampaignStatsResponse(
        rows=rows,
        total_spend=round(total_spend, 2),
        total_orders_money=round(total_om, 2),
        drr_pct=round(total_spend / total_om * 100, 2) if total_om else None,
        skipped_cabinets=skipped,
        source="api",
        note="Зеркало кабинета Ozon «Оплата за клик» по кампаниям (Performance "
             "API, сводка без дневного среза). Лимиты не расходует.",
    )
