"""
Универсальный движок «Что-Если» — считает эластичности (β) per товар
из РЕАЛЬНЫХ данных и симулирует сценарии.

ПРИНЦИП (юзер):
- где β реальный → возвращаем + R², n, confidence
- где данных мало → честно «не определимо», ориентир + ручной ввод

API:
  compute_betas(product_id, days=60) → BetasResult
  simulate(product_id, scenario_inputs, betas_override?) → SimulationResult
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.tax import calc_tax

UTC = timezone.utc


# ────────────────────────────────────────────────────────────────────
#  Регрессия log(y) = α + β log(x)
# ────────────────────────────────────────────────────────────────────

@dataclass
class BetaPoint:
    beta: float | None
    n: int
    r2: float | None
    confidence: str  # 'high' | 'medium' | 'low' | 'unknown' | 'no_data'
    note: str = ""


def _log_regression(xs: list[float], ys: list[float]) -> BetaPoint:
    pairs = [(math.log(xs[i]), math.log(ys[i]))
             for i in range(len(xs)) if xs[i] > 0 and ys[i] > 0]
    if len(pairs) < 5:
        return BetaPoint(beta=None, n=len(pairs), r2=None,
                         confidence="no_data",
                         note=f"только {len(pairs)} точек > 0, нужно ≥5")
    lx = [p[0] for p in pairs]; ly = [p[1] for p in pairs]
    n = len(pairs); mx = sum(lx)/n; my = sum(ly)/n
    num = sum((lx[i]-mx)*(ly[i]-my) for i in range(n))
    den = sum((lx[i]-mx)**2 for i in range(n))
    if den == 0:
        return BetaPoint(beta=None, n=n, r2=None, confidence="no_data",
                         note="нулевая дисперсия X")
    beta = num / den
    alpha = my - beta*mx
    ss_res = sum((ly[i] - (alpha + beta*lx[i]))**2 for i in range(n))
    ss_tot = sum((ly[i] - my)**2 for i in range(n))
    r2 = 1 - ss_res/ss_tot if ss_tot > 0 else None

    if r2 is None or r2 < 0.1:
        conf = "low"
        note = f"R²={r2:.2f} — большой шум, доверять нельзя" if r2 is not None else "R²?"
    elif r2 < 0.3:
        conf = "medium"
        note = f"R²={r2:.2f} — умеренная связь"
    else:
        conf = "high"
        note = f"R²={r2:.2f} — надёжная связь"
    return BetaPoint(beta=round(beta, 3), n=n, r2=round(r2, 3) if r2 is not None else None,
                     confidence=conf, note=note)


# ────────────────────────────────────────────────────────────────────
#  Compute betas for product
# ────────────────────────────────────────────────────────────────────

@dataclass
class BetasResult:
    product_id: str
    days_analyzed: int
    period_from: str
    period_to: str
    # Воронка
    imp_to_visits: BetaPoint
    visits_to_cart: BetaPoint
    cart_to_orders: BetaPoint
    orders_to_delivered: BetaPoint
    imp_to_orders: BetaPoint
    # Цена
    seller_price_to_orders: BetaPoint
    customer_price_to_orders: BetaPoint
    # Реклама
    ad_spend_to_imp: BetaPoint
    ad_spend_to_orders: BetaPoint
    # Снимок текущей базы для симуляции
    base: dict


async def compute_betas(db: AsyncSession, *, product_id: uuid.UUID, days: int = 60) -> BetasResult:
    period_to = datetime.now(UTC).date()
    period_from = period_to - timedelta(days=days)

    # Воронка из AnalyticsDaily
    rows = (await db.execute(text("""
        SELECT date,
               COALESCE(hits_view_search,0)+COALESCE(hits_view_pdp,0) imp,
               COALESCE(session_view_pdp,0) cv,
               COALESCE(hits_tocart_search,0)+COALESCE(hits_tocart_pdp,0) cart,
               COALESCE(ordered_units,0) orders,
               COALESCE(delivered_units,0) deliv
        FROM analytics_daily WHERE product_id = :pid AND date >= :df
    """), {"pid": str(product_id), "df": period_from})).all()
    imp = [float(r.imp) for r in rows]
    cv = [float(r.cv) for r in rows]
    cart = [float(r.cart) for r in rows]
    ords = [float(r.orders) for r in rows]
    deliv = [float(r.deliv) for r in rows]

    # Цены — из order_items
    rows = (await db.execute(text("""
        SELECT DATE(o.order_created_at) d,
               AVG(oi.price)::float avg_seller,
               AVG(oi.customer_price)::float avg_customer,
               COUNT(*) orders
        FROM order_items oi JOIN orders o ON o.id=oi.order_id
        WHERE oi.product_id = :pid AND o.status = 'delivered'
          AND o.order_created_at >= :df AND oi.price > 0
        GROUP BY 1
    """), {"pid": str(product_id), "df": period_from})).all()
    sp = [float(r.avg_seller) for r in rows]
    sp_orders = [float(r.orders) for r in rows]
    cp = [float(r.avg_customer) for r in rows if r.avg_customer]
    cp_orders = [float(r.orders) for r in rows if r.avg_customer]

    # Реклама
    rows = (await db.execute(text("""
        SELECT date, SUM(spend)::float spend,
               SUM(impressions)::bigint imp, SUM(orders)::bigint ord
        FROM ad_statistics WHERE product_id = :pid AND date >= :df
        GROUP BY date HAVING SUM(spend) > 0
    """), {"pid": str(product_id), "df": period_from})).all()
    ad_spend = [float(r.spend) for r in rows]
    ad_imp = [float(r.imp) for r in rows]
    ad_ord = [float(r.ord) for r in rows]

    # База для симуляции — суммарные значения за период
    base_imp = sum(imp); base_cv = sum(cv); base_cart = sum(cart)
    base_orders = sum(ords); base_deliv = sum(deliv)
    base_ad_spend = sum(ad_spend); base_ad_imp = sum(ad_imp)
    base_avg_seller = (sum(sp)/len(sp)) if sp else None
    base_avg_customer = (sum(cp)/len(cp)) if cp else None

    return BetasResult(
        product_id=str(product_id),
        days_analyzed=days,
        period_from=period_from.isoformat(),
        period_to=period_to.isoformat(),
        imp_to_visits=_log_regression(imp, cv),
        visits_to_cart=_log_regression(cv, cart),
        cart_to_orders=_log_regression(cart, ords),
        orders_to_delivered=_log_regression(ords, deliv),
        imp_to_orders=_log_regression(imp, ords),
        seller_price_to_orders=_log_regression(sp, sp_orders),
        customer_price_to_orders=_log_regression(cp, cp_orders),
        ad_spend_to_imp=_log_regression(ad_spend, ad_imp),
        ad_spend_to_orders=_log_regression(ad_spend, ad_ord),
        base={
            "impressions": int(base_imp),
            "card_visits": int(base_cv),
            "to_cart": int(base_cart),
            "orders": int(base_orders),
            "delivered": int(base_deliv),
            "ad_spend": round(base_ad_spend, 2),
            "ad_imp": int(base_ad_imp),
            "avg_seller_price": round(base_avg_seller, 2) if base_avg_seller else None,
            "avg_customer_price": round(base_avg_customer, 2) if base_avg_customer else None,
            "cr_imp_to_visit": round(base_cv/base_imp, 4) if base_imp else None,
            "cr_visit_to_cart": round(base_cart/base_cv, 4) if base_cv else None,
            "cr_cart_to_order": round(base_orders/base_cart, 4) if base_cart else None,
            "cr_order_to_delivered": round(base_deliv/base_orders, 4) if base_orders else None,
        },
    )


# ────────────────────────────────────────────────────────────────────
#  Simulate scenario
# ────────────────────────────────────────────────────────────────────

@dataclass
class ScenarioInput:
    name: str
    ad_spend_pct: float = 0.0           # %-изменение рекл-бюджета
    seller_price_pct: float = 0.0       # %-изменение цены продавца
    impressions_pct: float = 0.0        # %-изменение трафика (помимо рекламы)
    cr_cart_to_order_pct: float = 0.0   # ручная правка конверсии
    cost_pct: float = 0.0               # %-изменение себестоимости
    # Гипотезы эластичностей (если юзер хочет поиграть)
    override_beta_price: float | None = None
    override_beta_ad_to_imp: float | None = None


@dataclass
class ScenarioOutput:
    name: str
    impressions: int
    card_visits: int
    to_cart: int
    orders: int
    delivered: int
    seller_price: float
    revenue: float
    ad_spend: float
    drr_pct: float | None
    cost_total: float
    commission_total: float
    logistics_total: float
    acquiring_total: float
    operating_profit: float
    tax_amount: float
    net_profit: float
    net_margin_pct: float | None
    delta_net_vs_base: float  # абсолютная дельта чистой прибыли vs текущее
    drivers_explanation: list[str]  # «текст: почему такая прибыль»


def simulate_scenario(
    *,
    base: dict,
    seller_price: float,
    cost: float,
    commission_pct: float,
    tax_regime: str,
    tax_rate: float,
    vat_rate: float | None,
    betas: BetasResult,
    scenario: ScenarioInput,
    base_net_profit: float,
) -> ScenarioOutput:
    explain: list[str] = []

    # 1. Реклама → показы
    new_ad_spend = (base["ad_spend"] or 0) * (1 + scenario.ad_spend_pct / 100)
    β_ad = (scenario.override_beta_ad_to_imp
            if scenario.override_beta_ad_to_imp is not None
            else (betas.ad_spend_to_imp.beta if betas.ad_spend_to_imp.beta else 0.8))
    if base["ad_spend"] and new_ad_spend > 0:
        ad_mult = (new_ad_spend / base["ad_spend"]) ** β_ad if base["ad_spend"] > 0 else 1
        new_ad_imp = (base["ad_imp"] or 0) * ad_mult
        if scenario.ad_spend_pct != 0:
            explain.append(f"реклама ×{1+scenario.ad_spend_pct/100:.2f} → показы ×{ad_mult:.2f} (β_реклама={β_ad:+.2f})")
    else:
        new_ad_imp = base["ad_imp"] or 0

    # 2. Общие показы (рекл + органика + ручка)
    organic_imp = max((base["impressions"] or 0) - (base["ad_imp"] or 0), 0)
    new_imp = organic_imp + new_ad_imp
    new_imp = new_imp * (1 + scenario.impressions_pct / 100)
    if scenario.impressions_pct != 0:
        explain.append(f"трафик ×{1+scenario.impressions_pct/100:.2f}")

    # 3. Цена → спрос (демпфер: если β есть и надёжный, иначе игнорируем)
    new_price = seller_price * (1 + scenario.seller_price_pct / 100)
    β_price = (scenario.override_beta_price
               if scenario.override_beta_price is not None
               else None)
    # Используем override юзера — если не задан, эффекта цены НЕТ (мы не подсовываем -1.0)
    demand_mult_price = 1.0
    if β_price is not None and scenario.seller_price_pct != 0:
        demand_mult_price = (seller_price / new_price) ** β_price if new_price > 0 else 1
        explain.append(f"цена ×{1+scenario.seller_price_pct/100:.2f} → спрос ×{demand_mult_price:.2f} (твоя гипотеза β={β_price:.2f})")
    elif scenario.seller_price_pct != 0:
        explain.append(f"цена ×{1+scenario.seller_price_pct/100:.2f} — без эффекта на спрос (β цены на твоих данных не определима)")

    # 4. Прогон по воронке (используем РЕАЛЬНЫЕ конверсии Жирафа)
    cr1 = base["cr_imp_to_visit"] or 0
    cr2 = base["cr_visit_to_cart"] or 0
    cr3 = (base["cr_cart_to_order"] or 0) * (1 + scenario.cr_cart_to_order_pct / 100)
    cr4 = base["cr_order_to_delivered"] or 0

    visits = new_imp * cr1
    carts = visits * cr2
    orders = carts * cr3 * demand_mult_price
    delivered = orders * cr4

    if scenario.cr_cart_to_order_pct != 0:
        explain.append(f"конверсия в заказ ×{1+scenario.cr_cart_to_order_pct/100:.2f}")

    # 5. Финансы
    new_cost = cost * (1 + scenario.cost_pct / 100)
    if scenario.cost_pct != 0:
        explain.append(f"себестоимость ×{1+scenario.cost_pct/100:.2f}")

    revenue = delivered * new_price
    commission = revenue * commission_pct / 100
    logistics = delivered * 306.0
    acquiring = revenue * 0.015
    cost_total = delivered * new_cost
    op_profit = revenue - commission - logistics - acquiring - cost_total - new_ad_spend
    tax = calc_tax(revenue=revenue, gross_profit=op_profit,
                   tax_regime=tax_regime, tax_rate_pct=tax_rate, vat_rate_pct=vat_rate)

    drr = (new_ad_spend / revenue * 100) if revenue > 0 else None
    net_margin = (tax.net_profit / revenue * 100) if revenue > 0 else None

    return ScenarioOutput(
        name=scenario.name,
        impressions=int(round(new_imp)),
        card_visits=int(round(visits)),
        to_cart=int(round(carts)),
        orders=int(round(orders)),
        delivered=int(round(delivered)),
        seller_price=round(new_price, 2),
        revenue=round(revenue, 2),
        ad_spend=round(new_ad_spend, 2),
        drr_pct=round(drr, 2) if drr is not None else None,
        cost_total=round(cost_total, 2),
        commission_total=round(commission, 2),
        logistics_total=round(logistics, 2),
        acquiring_total=round(acquiring, 2),
        operating_profit=round(op_profit, 2),
        tax_amount=round(tax.tax_amount + tax.vat_amount, 2),
        net_profit=tax.net_profit,
        net_margin_pct=round(net_margin, 2) if net_margin is not None else None,
        delta_net_vs_base=round(tax.net_profit - base_net_profit, 2),
        drivers_explanation=explain,
    )
