"""
analytics_engine — сборщик «полного контекста» товара/кабинета для AI и debug.

Принцип юзера: AI знает контекст страницы + берёт ШИРОКИЕ данные из БД
(не только экранную метрику) → формулы → ответ с вариантами решения.

get_full_context(product_id, days=30) возвращает JSON со ВСЕМ:
- карточка товара (price/cost/sales_percent_fbo/...)
- продажи за период (qty/revenue/avg_seller_price/avg_customer_price)
- расходы (commission/logistics/acquiring/ad)
- чистая прибыль (через services/tax)
- остатки на складах
- воронка (показы→заказы)
- реклама (spend/CTR/ДРР)
- стокаут-сигнал
- последние 5 «худших» дней с факторами

Этот JSON — input для AI («Почему просел Жираф?») И для всех страниц-агрегаторов.
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, Product
from app.services.finance_consts import (
    DEFAULT_COMMISSION_PCT,
    LOGISTICS_PER_UNIT,  # для отображения как «эвристика»
    calc_acquiring,
    calc_logistics,
    get_commission_pct,
)
from app.services.tax import calc_tax

UTC = timezone.utc


async def get_full_context(
    db: AsyncSession,
    *,
    product_id: uuid.UUID,
    company_id: uuid.UUID,
    days: int = 30,
) -> dict[str, Any]:
    """Полный контекст товара за период — всё что нужно AI или агрегатору."""
    today = datetime.now(UTC).date()
    date_from = today - timedelta(days=days)

    # ─── Карточка товара ───
    prod = (await db.execute(text("""
        SELECT p.*, a.name AS cabinet_name
        FROM products p JOIN ozon_accounts a ON a.id = p.ozon_account_id
        WHERE p.id = :pid AND a.company_id = :cid
    """), {"pid": str(product_id), "cid": str(company_id)})).first()
    if not prod:
        return {"error": "product not found"}

    seller_price = float(prod.marketing_price or prod.current_price or 0)
    cost = float(prod.cost_price) if prod.cost_price else None
    commission_pct = get_commission_pct(product_sales_percent_fbo=prod.sales_percent_fbo)
    prod_acq_amount = float(prod.acquiring_amount) if getattr(prod, "acquiring_amount", None) else None

    # ─── Продажи за период ───
    sales = (await db.execute(text("""
        SELECT COUNT(*) qty, SUM(oi.price)::float revenue,
               AVG(oi.price)::float avg_seller_price,
               AVG(oi.customer_price)::float avg_customer_price,
               COUNT(*) FILTER (WHERE oi.customer_price IS NOT NULL) cust_price_n
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE oi.product_id = :pid AND o.status = 'delivered'
          AND o.order_created_at >= :df
          AND oi.price > 0
    """), {"pid": str(product_id), "df": date_from})).first()
    qty = int(sales.qty or 0)
    revenue = float(sales.revenue or 0)
    avg_seller = float(sales.avg_seller_price) if sales.avg_seller_price else None
    avg_customer = float(sales.avg_customer_price) if sales.avg_customer_price else None

    # ─── Налог компании ───
    company = (await db.execute(
        select(Company).where(Company.id == company_id)
    )).scalar_one()
    tax_regime = company.tax_regime or "usn_income"
    tax_rate = float(company.tax_rate_pct or 6.0)
    vat_rate = float(company.vat_rate_pct) if company.vat_rate_pct else None

    # ─── Реклама за период ───
    ad = (await db.execute(text("""
        SELECT SUM(spend)::float spend, SUM(views)::bigint imp,
               SUM(clicks)::bigint clicks, SUM(orders)::bigint orders
        FROM ad_product_daily WHERE product_id = :pid AND date >= :df
    """), {"pid": str(product_id), "df": date_from})).first()
    ad_spend = float(ad.spend or 0) if ad else 0.0

    # ─── Возвраты за период (по return_date — "зеркало Ozon") ───
    returned_revenue_row = (await db.execute(text("""
        SELECT COALESCE(SUM(return_amount), 0)::float
        FROM returns
        WHERE product_id = :pid
          AND return_date >= :df
    """), {"pid": str(product_id), "df": date_from})).scalar() or 0
    returned_revenue = float(returned_revenue_row)
    effective_revenue = revenue - returned_revenue

    # ─── Расходы ───
    cost_total = (cost or 0) * qty
    comm_total = revenue * commission_pct / 100
    # База эквайринга/логистики — средняя seller_price × qty. Тождественно revenue
    # для одного товара, но через helper остаётся явная точка перехода на Product.acquiring_amount/Transaction.
    log_calc = calc_logistics(qty=qty)
    acq_calc = calc_acquiring(
        seller_price=avg_seller or seller_price, qty=qty,
        product_acquiring_amount=prod_acq_amount,
    )
    log_total = log_calc.amount
    acq_total = acq_calc.amount
    # ВАЖНО: op_profit и налог считаются от effective_revenue (после возвратов)
    op_profit = effective_revenue - cost_total - comm_total - log_total - acq_total - ad_spend
    tax_res = calc_tax(
        revenue=effective_revenue, gross_profit=op_profit,
        tax_regime=tax_regime, tax_rate_pct=tax_rate, vat_rate_pct=vat_rate,
    )

    # ─── Остатки на складах ───
    stocks = (await db.execute(text("""
      WITH last_wh AS (
        SELECT MAX(time) t FROM stocks
        WHERE product_id = :pid AND warehouse_type='FBO_WH'
      ),
      last_agg AS (
        SELECT MAX(time) t FROM stocks
        WHERE product_id = :pid AND warehouse_type IN ('AGG','FBO','FBS')
      )
      SELECT
        (SELECT SUM(GREATEST(free_to_sell - reserved, 0))
         FROM stocks WHERE product_id = :pid AND time = (SELECT t FROM last_wh) AND warehouse_type='FBO_WH') wh_total,
        (SELECT SUM(GREATEST(free_to_sell - reserved, 0))
         FROM stocks WHERE product_id = :pid AND time = (SELECT t FROM last_agg) AND warehouse_type='AGG') agg_total,
        (SELECT MAX(time) FROM stocks WHERE product_id = :pid) last_snap
    """), {"pid": str(product_id)})).first()
    stock_wh = int(stocks.wh_total or 0) if stocks else 0
    stock_agg = int(stocks.agg_total or 0) if stocks else 0
    current_stock = stock_wh if stock_wh > 0 else stock_agg

    # ─── Воронка ───
    funnel = (await db.execute(text("""
        SELECT SUM(COALESCE(hits_view, hits_view_search + hits_view_pdp))::bigint impressions,
               SUM(session_view_pdp)::bigint card_visits,
               SUM(hits_tocart_search + hits_tocart_pdp)::bigint to_cart,
               SUM(ordered_units)::bigint orders,
               SUM(delivered_units)::bigint delivered
        FROM analytics_daily WHERE product_id = :pid AND date >= :df
    """), {"pid": str(product_id), "df": date_from})).first()

    return {
        "product": {
            "id": str(product_id),
            "name": prod.name,
            "offer_id": prod.offer_id,
            "ozon_sku": prod.ozon_sku,
            "cabinet_name": prod.cabinet_name,
            "is_archived": bool(prod.is_archived),
            "is_hot": bool(prod.is_hot),
            "category_name": prod.category_name,
            "tags": prod.tags or [],
        },
        "pricing": {
            "seller_price": seller_price,
            "current_price_struck_through": float(prod.current_price) if prod.current_price else None,
            "min_price": float(prod.min_price) if prod.min_price else None,
            "cost_price": cost,
            "commission_pct": commission_pct,
            "avg_customer_price_30d": avg_customer,
            "spp_pct": round((1 - avg_customer / seller_price) * 100, 1)
                       if avg_customer and seller_price else None,
        },
        "sales": {
            "period_days": days,
            "qty_delivered": qty,
            "revenue": round(revenue, 2),
            "avg_seller_price": round(avg_seller, 2) if avg_seller else None,
            "customer_price_data_coverage_pct": round(
                100 * (sales.cust_price_n or 0) / qty, 1) if qty else None,
        },
        "returns": {
            "returned_revenue": round(returned_revenue, 2),
            "effective_revenue": round(effective_revenue, 2),
        },
        "expenses": {
            "cost_total": round(cost_total, 2),
            "commission_total": round(comm_total, 2),
            "logistics_total": round(log_total, 2),
            "logistics_source": log_calc.source,  # "real" / "estimate"
            "acquiring_total": round(acq_total, 2),
            "acquiring_source": acq_calc.source,  # "api" / "estimate"
            "ad_spend": round(ad_spend, 2),
        },
        "profit": {
            "operating_profit": round(op_profit, 2),
            "tax_regime": tax_regime,
            "tax_regime_label": tax_res.regime_label,
            "tax_rate_pct": tax_rate,
            "tax_amount": tax_res.tax_amount,
            "vat_amount": tax_res.vat_amount,
            "net_profit": tax_res.net_profit,
            "net_margin_pct": round(tax_res.net_profit / revenue * 100, 2) if revenue else None,
        },
        "stocks": {
            "current_total": current_stock,
            "by_fbo_wh": stock_wh,
            "by_agg": stock_agg,
            "is_stockout": current_stock == 0,
            "last_snapshot_at": stocks.last_snap.isoformat() if stocks and stocks.last_snap else None,
        },
        "funnel": {
            "impressions": int(funnel.impressions or 0) if funnel else 0,
            "card_visits": int(funnel.card_visits or 0) if funnel else 0,
            "to_cart": int(funnel.to_cart or 0) if funnel else 0,
            "orders": int(funnel.orders or 0) if funnel else 0,
            "delivered": int(funnel.delivered or 0) if funnel else 0,
            "ctr_pct": round((funnel.card_visits or 0) / (funnel.impressions or 1) * 100, 2)
                       if funnel and funnel.impressions else None,
            "cart_to_order_pct": round((funnel.orders or 0) / (funnel.to_cart or 1) * 100, 2)
                       if funnel and funnel.to_cart else None,
        },
        "advertising": {
            "spend": ad_spend,
            "impressions": int(ad.imp or 0) if ad else 0,
            "clicks": int(ad.clicks or 0) if ad else 0,
            "orders": int(ad.orders or 0) if ad else 0,
            "drr_pct": round(ad_spend / revenue * 100, 2) if revenue else None,
        },
        "context_generated_at": datetime.now(UTC).isoformat(),
    }
