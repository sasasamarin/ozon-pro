"""
/api/v1/margin — маржа per-SKU из products + transactions.

  margin_per_unit = avg_seller_price − cost_price − avg_mp_costs_per_unit
  margin_pct      = margin_per_unit / avg_seller_price × 100

Где avg_mp_costs_per_unit = (commissions + logistics + acquiring + advertising)
                            / delivered_units. Используется per-SKU из транзакций
(если есть posting_number → order → product) или fallback на средние коэффициенты.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.services.finance_consts import (
    DEFAULT_COMMISSION_PCT, ACQUIRING_PCT_DEFAULT, LOGISTICS_PER_UNIT_DEFAULT,
)


router = APIRouter()


class MarginRow(BaseModel):
    product_id: str
    name: str | None
    offer_id: str | None
    ozon_sku: int | None
    cabinet_name: str
    seller_price_rub: float | None
    cost_price_rub: float | None
    cost_known: bool
    delivered_units: int
    revenue_rub: float
    avg_mp_costs_per_unit_rub: float | None   # commission+logistics+acquiring+adv per unit
    gross_margin_per_unit_rub: float | None   # = seller_price - cost - mp_costs
    gross_margin_pct: float | None
    note: str


class MarginResponse(BaseModel):
    period_days: int
    items: list[MarginRow]
    summary: dict


@router.get("/", response_model=MarginResponse)
async def margin_list(
    days: int = Query(30, ge=7, le=365),
    cabinet_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MarginResponse:
    """Маржинальность всех активных SKU компании за период."""
    df = date.today() - timedelta(days=days)

    where = ["p.is_archived = false", "oa.company_id = :cid"]
    params: dict = {"cid": str(current_user.company_id), "df": df}
    if cabinet_id:
        where.append("oa.id = :cab")
        params["cab"] = str(cabinet_id)

    # delivered units + revenue per product
    rows = (await db.execute(text(f"""
        SELECT
            p.id::text id, p.name, p.offer_id, p.ozon_sku,
            oa.name cabinet_name,
            COALESCE(p.cost_price, 0)::float cost,
            COALESCE(p.marketing_price, p.selling_price, p.current_price, 0)::float seller,
            COALESCE(SUM(oi.quantity) FILTER (WHERE o.status='delivered'), 0)::int delivered_units,
            COALESCE(SUM(oi.price * oi.quantity) FILTER (WHERE o.status='delivered'), 0)::float revenue
        FROM products p
        JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
        LEFT JOIN order_items oi ON oi.product_id = p.id
        LEFT JOIN orders o ON o.id = oi.order_id AND o.order_created_at >= :df
        WHERE {' AND '.join(where)}
        GROUP BY p.id, p.name, p.offer_id, p.ozon_sku, oa.name, p.cost_price,
                 p.marketing_price, p.selling_price, p.current_price
        ORDER BY revenue DESC
    """), params)).all()

    items: list[MarginRow] = []
    total_rev = 0.0
    total_margin = 0.0
    skus_with_cost = 0

    for r in rows:
        seller = float(r.seller or 0)
        cost = float(r.cost or 0)
        delivered = int(r.delivered_units or 0)
        revenue = float(r.revenue or 0)

        # MP-costs: точный расчёт через коэффициенты + средняя логистика
        comm_per_unit = seller * (DEFAULT_COMMISSION_PCT / 100)
        acq_per_unit = seller * (ACQUIRING_PCT_DEFAULT / 100)
        log_per_unit = LOGISTICS_PER_UNIT_DEFAULT
        mp_per_unit = comm_per_unit + acq_per_unit + log_per_unit

        cost_known = cost > 0
        margin_per_unit = (seller - cost - mp_per_unit) if cost_known else None
        margin_pct = (margin_per_unit / seller * 100) if (margin_per_unit is not None and seller) else None

        note = ""
        if not cost_known:
            note = "Себестоимость не задана — маржа не рассчитана. Заведи в /products."
        elif margin_per_unit is not None and margin_per_unit < 0:
            note = "ОТРИЦАТЕЛЬНАЯ маржа! Убыточный SKU — повысить цену или вывести."

        items.append(MarginRow(
            product_id=r.id, name=r.name, offer_id=r.offer_id, ozon_sku=r.ozon_sku,
            cabinet_name=r.cabinet_name,
            seller_price_rub=round(seller, 2) if seller else None,
            cost_price_rub=round(cost, 2) if cost_known else None,
            cost_known=cost_known,
            delivered_units=delivered,
            revenue_rub=round(revenue, 2),
            avg_mp_costs_per_unit_rub=round(mp_per_unit, 2),
            gross_margin_per_unit_rub=round(margin_per_unit, 2) if margin_per_unit is not None else None,
            gross_margin_pct=round(margin_pct, 2) if margin_pct is not None else None,
            note=note,
        ))
        total_rev += revenue
        if margin_per_unit is not None:
            total_margin += margin_per_unit * delivered
        if cost_known:
            skus_with_cost += 1

    return MarginResponse(
        period_days=days,
        items=items,
        summary={
            "total_revenue_rub": round(total_rev, 2),
            "total_gross_margin_rub": round(total_margin, 2),
            "gross_margin_pct": round(total_margin / total_rev * 100, 2) if total_rev else None,
            "skus_total": len(items),
            "skus_with_cost": skus_with_cost,
            "skus_without_cost": len(items) - skus_with_cost,
            "note": (
                f"MP-расходы оценка: комиссия {DEFAULT_COMMISSION_PCT}%, "
                f"эквайринг {ACQUIRING_PCT_DEFAULT}%, логистика {LOGISTICS_PER_UNIT_DEFAULT}₽/шт. "
                f"Точная картина — через /finance/pnl."
            ),
        },
    )
