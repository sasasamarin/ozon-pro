"""
«Экономика продаж» — единая P&L-таблица по товарам (nepsell-канон).

Колонки на единицу + итог за период:
- qty_delivered (выкупленные единицы)
- avg_seller_price (≈ accruals_for_sale — выручка продавца за единицу)
- avg_customer_price (≈ что физически платил покупатель с СПП)
- cost_per_unit (себестоимость закупки)
- commission_per_unit (Ozon-комиссия % × seller_price)
- logistics_per_unit (~306 ₽ — delivery + last_mile)
- acquiring_per_unit (1.5% от seller_price)
- ad_spend_per_unit (AdStatistics.spend / qty)
- operating_profit (выручка − все вычеты)
- tax (по компании-режиму через services/tax.py)
- net_profit (после налога) и net_margin %

GET /api/v1/products/economics?days=30&product_id=...&cabinet_ids=...
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Company, OzonAccount, Product, User
from app.services.tax import calc_tax

router = APIRouter()
UTC = timezone.utc

# Эвристики для расходов на единицу
LOGISTICS_PER_UNIT = 306.0
ACQUIRING_PCT = 1.5
DEFAULT_COMMISSION_PCT = 25.0


class EconomicsRow(BaseModel):
    product_id: str
    product_name: str
    offer_id: str
    ozon_sku: int
    cabinet_name: str
    is_archived: bool

    qty_delivered: int
    revenue: float

    # На единицу — для сравнения товаров
    avg_seller_price: float | None
    avg_customer_price: float | None     # СПП-цена покупателя (если есть customer_price)
    spp_pct: float | None                # на сколько % покупатель видит ниже seller_price

    cost_per_unit: float | None
    commission_pct: float                 # реальная sales_percent_fbo (или fallback)
    commission_per_unit: float
    logistics_per_unit: float
    acquiring_per_unit: float
    ad_spend_per_unit: float

    # Итоги за период (× qty)
    cost_total: float
    commission_total: float
    logistics_total: float
    acquiring_total: float
    ad_spend_total: float
    operating_profit: float               # выручка минус все вычеты, ДО налога
    operating_margin_pct: float | None

    tax_amount: float
    vat_amount: float
    net_profit: float                     # ПОСЛЕ налога
    net_margin_pct: float | None

    cost_missing: bool                    # cost_price пуст → итоги неполные


class EconomicsTotals(BaseModel):
    qty_delivered: int
    revenue: float
    cost_total: float
    commission_total: float
    logistics_total: float
    acquiring_total: float
    ad_spend_total: float
    operating_profit: float
    tax_amount: float
    vat_amount: float
    net_profit: float
    net_margin_pct: float | None
    products_total: int
    products_with_cost: int               # сколько товаров имеют cost_price
    products_missing_cost: int


class EconomicsResp(BaseModel):
    period_from: str
    period_to: str
    tax_regime: str
    tax_regime_label: str
    tax_rate_pct: float
    rows: list[EconomicsRow]
    totals: EconomicsTotals


@router.get("/", response_model=EconomicsResp)
async def get_economics(
    days: int = Query(30, ge=1, le=365),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    product_id: uuid.UUID | None = Query(None),
    include_archived: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EconomicsResp:
    # Период
    today = datetime.now(UTC).date()
    if not date_to:
        date_to = today
    if not date_from:
        date_from = date_to - timedelta(days=days)

    # Налог компании
    company = (await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )).scalar_one()
    tax_regime = company.tax_regime or "usn_income"
    tax_rate = float(company.tax_rate_pct or 6.0)
    vat_rate = float(company.vat_rate_pct) if company.vat_rate_pct else None

    # Список разрешённых кабинетов
    cab_q = select(OzonAccount.id, OzonAccount.name).where(
        OzonAccount.company_id == current_user.company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if cabinet_ids:
        cab_q = cab_q.where(OzonAccount.id.in_(cabinet_ids))
    cab_rows = (await db.execute(cab_q)).all()
    if not cab_rows:
        return EconomicsResp(
            period_from=date_from.isoformat(), period_to=date_to.isoformat(),
            tax_regime=tax_regime, tax_regime_label=tax_regime.upper(),
            tax_rate_pct=tax_rate, rows=[], totals=_empty_totals(),
        )
    allowed_acc_ids = [r[0] for r in cab_rows]
    acc_name_map = {r[0]: r[1] for r in cab_rows}

    # Per-product агрегация заказов за период (только доставленные)
    where_extra = ""
    params: dict = {
        "accs": [str(x) for x in allowed_acc_ids],
        "df": date_from, "dt": date_to,
    }
    if product_id is not None:
        where_extra = "AND oi.product_id = :pid"
        params["pid"] = str(product_id)
    if not include_archived:
        where_extra += " AND p.is_archived = false"

    sql = f"""
        SELECT
            p.id::text AS product_id,
            p.name, p.offer_id, p.ozon_sku, p.is_archived,
            p.ozon_account_id::text AS account_id,
            p.cost_price::float                AS cost_price,
            p.sales_percent_fbo::float         AS comm_pct,
            COUNT(*)                            AS qty_delivered,
            SUM(oi.price)::float                AS revenue,
            AVG(oi.price)::float                AS avg_seller_price,
            AVG(oi.customer_price)::float       AS avg_customer_price
        FROM order_items oi
        JOIN orders o   ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        WHERE o.ozon_account_id = ANY(:accs)
          AND o.order_created_at >= :df
          AND o.order_created_at < (CAST(:dt AS date) + interval '1 day')
          AND o.status = 'delivered'
          AND oi.price > 0
          {where_extra}
        GROUP BY p.id, p.name, p.offer_id, p.ozon_sku, p.is_archived,
                 p.ozon_account_id, p.cost_price, p.sales_percent_fbo
        ORDER BY revenue DESC NULLS LAST
    """
    rows = (await db.execute(text(sql), params)).all()

    # ad_spend per-product за тот же период
    ad_rows = (await db.execute(text("""
        SELECT product_id::text pid, SUM(spend)::float spend
        FROM ad_statistics
        WHERE ozon_account_id = ANY(:accs)
          AND date >= :df AND date <= :dt
        GROUP BY product_id
    """), {"accs": params["accs"], "df": date_from, "dt": date_to})).all()
    ad_by_prod: dict[str, float] = {r.pid: float(r.spend or 0) for r in ad_rows}

    # Построение строк
    out_rows: list[EconomicsRow] = []
    tot_qty = 0
    tot_revenue = tot_cost = tot_comm = tot_log = tot_acq = tot_ad = 0.0
    tot_op = tot_tax = tot_vat = tot_net = 0.0
    p_with_cost = 0

    for r in rows:
        qty = int(r.qty_delivered or 0)
        revenue = float(r.revenue or 0)
        if qty == 0 or revenue == 0:
            continue

        avg_seller = float(r.avg_seller_price) if r.avg_seller_price else None
        avg_customer = float(r.avg_customer_price) if r.avg_customer_price else None
        spp_pct = None
        if avg_seller and avg_customer and avg_seller > 0 and avg_customer < avg_seller:
            spp_pct = round((1 - avg_customer / avg_seller) * 100, 1)

        cost_per = float(r.cost_price) if r.cost_price else None
        commission_pct = float(r.comm_pct) if r.comm_pct else DEFAULT_COMMISSION_PCT
        comm_per = (avg_seller or 0) * commission_pct / 100
        acq_per = (avg_seller or 0) * ACQUIRING_PCT / 100
        ad_total = ad_by_prod.get(r.product_id, 0.0)
        ad_per = ad_total / qty if qty else 0.0

        cost_total = (cost_per * qty) if cost_per else 0.0
        comm_total = comm_per * qty
        log_total = LOGISTICS_PER_UNIT * qty
        acq_total = acq_per * qty

        op_profit = revenue - cost_total - comm_total - log_total - acq_total - ad_total
        tax_res = calc_tax(
            revenue=revenue, gross_profit=op_profit,
            tax_regime=tax_regime, tax_rate_pct=tax_rate, vat_rate_pct=vat_rate,
        )

        net = tax_res.net_profit
        net_margin = (net / revenue * 100) if revenue else None
        op_margin = (op_profit / revenue * 100) if revenue else None

        out_rows.append(EconomicsRow(
            product_id=r.product_id,
            product_name=r.name,
            offer_id=r.offer_id,
            ozon_sku=r.ozon_sku,
            cabinet_name=acc_name_map.get(uuid.UUID(r.account_id), "—"),
            is_archived=bool(r.is_archived),
            qty_delivered=qty,
            revenue=round(revenue, 2),
            avg_seller_price=round(avg_seller, 2) if avg_seller else None,
            avg_customer_price=round(avg_customer, 2) if avg_customer else None,
            spp_pct=spp_pct,
            cost_per_unit=cost_per,
            commission_pct=round(commission_pct, 2),
            commission_per_unit=round(comm_per, 2),
            logistics_per_unit=LOGISTICS_PER_UNIT,
            acquiring_per_unit=round(acq_per, 2),
            ad_spend_per_unit=round(ad_per, 2),
            cost_total=round(cost_total, 2),
            commission_total=round(comm_total, 2),
            logistics_total=round(log_total, 2),
            acquiring_total=round(acq_total, 2),
            ad_spend_total=round(ad_total, 2),
            operating_profit=round(op_profit, 2),
            operating_margin_pct=round(op_margin, 2) if op_margin is not None else None,
            tax_amount=tax_res.tax_amount,
            vat_amount=tax_res.vat_amount,
            net_profit=net,
            net_margin_pct=round(net_margin, 2) if net_margin is not None else None,
            cost_missing=cost_per is None,
        ))

        tot_qty += qty
        tot_revenue += revenue
        tot_cost += cost_total
        tot_comm += comm_total
        tot_log += log_total
        tot_acq += acq_total
        tot_ad += ad_total
        tot_op += op_profit
        tot_tax += tax_res.tax_amount
        tot_vat += tax_res.vat_amount
        tot_net += net
        if cost_per is not None:
            p_with_cost += 1

    totals = EconomicsTotals(
        qty_delivered=tot_qty,
        revenue=round(tot_revenue, 2),
        cost_total=round(tot_cost, 2),
        commission_total=round(tot_comm, 2),
        logistics_total=round(tot_log, 2),
        acquiring_total=round(tot_acq, 2),
        ad_spend_total=round(tot_ad, 2),
        operating_profit=round(tot_op, 2),
        tax_amount=round(tot_tax, 2),
        vat_amount=round(tot_vat, 2),
        net_profit=round(tot_net, 2),
        net_margin_pct=round(tot_net / tot_revenue * 100, 2) if tot_revenue else None,
        products_total=len(out_rows),
        products_with_cost=p_with_cost,
        products_missing_cost=len(out_rows) - p_with_cost,
    )

    return EconomicsResp(
        period_from=date_from.isoformat(),
        period_to=date_to.isoformat(),
        tax_regime=tax_regime,
        tax_regime_label={
            "usn_income": "УСН Доходы",
            "usn_income_minus": "УСН Доходы-Расходы",
            "osno": "ОСНО",
            "none": "Без налога",
        }.get(tax_regime, tax_regime),
        tax_rate_pct=tax_rate,
        rows=out_rows, totals=totals,
    )


def _empty_totals() -> EconomicsTotals:
    return EconomicsTotals(
        qty_delivered=0, revenue=0, cost_total=0, commission_total=0,
        logistics_total=0, acquiring_total=0, ad_spend_total=0,
        operating_profit=0, tax_amount=0, vat_amount=0, net_profit=0,
        net_margin_pct=None, products_total=0,
        products_with_cost=0, products_missing_cost=0,
    )
