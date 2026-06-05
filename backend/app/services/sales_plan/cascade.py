"""
Каскадный пересчёт зависимостей метрик.

Граф зависимостей:
  показы → CTR → клики → конверсия → заказы → %выкупа → продажи → выручка
  − комиссия − логистика − эквайринг − реклама − возвраты = марж.прибыль
  − налог − OPEX = чистая прибыль
  реклама(бюджет) → клики↑ → заказы↑
  реклама → ДРР↑ → маржа↓

simulate_plan_change(metric, delta):
  «+10000 кликов» → +заказы, +выручка, ДРР с a→b, маржа ±Y, CPC break-even
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class CascadeEffect:
    """Один эффект изменения метрики на другую."""
    metric: str
    delta: float
    new_value: float | None
    explanation: str


@dataclass
class CascadeResult:
    input_metric: str
    input_delta: float
    base_period: tuple[date, date]
    effects: list[CascadeEffect]
    cpc_breakeven: float | None
    drr_before_pct: float | None
    drr_after_pct: float | None
    note: str


async def _get_base_metrics(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    period_start: date,
    period_end: date,
    cabinet_id: uuid.UUID | None = None,
) -> dict[str, float]:
    """Берём средние коэффициенты из истории компании за период."""
    extra = ""
    params = {"cid": str(company_id), "df": period_start, "dt": period_end}
    if cabinet_id:
        extra = "AND oa.id = :cab"
        params["cab"] = str(cabinet_id)

    # Базовые метрики из transactions + orders
    row = (await db.execute(text(f"""
        SELECT
            COALESCE(SUM(t.accruals_for_sale) FILTER (WHERE t.operation_type='OperationAgentDeliveredToCustomer'), 0)::float AS revenue,
            COALESCE(SUM(ABS(t.advertising)), 0)::float AS ad_spend,
            COALESCE(SUM(ABS(t.sale_commission)), 0)::float AS commission,
            COALESCE(SUM(ABS(t.delivery_to_customer)), 0)::float AS logistics,
            COALESCE(SUM(ABS(t.acquiring)), 0)::float AS acquiring
        FROM transactions t
        JOIN ozon_accounts oa ON oa.id = t.ozon_account_id
        WHERE oa.company_id = :cid
          AND t.operation_date >= :df AND t.operation_date <= :dt
          {extra}
    """), params)).first()

    orders_row = (await db.execute(text(f"""
        SELECT COUNT(*)::float AS orders,
               COALESCE(AVG(o.total_amount), 0)::float AS aov
        FROM orders o
        JOIN ozon_accounts oa ON oa.id = o.ozon_account_id
        WHERE oa.company_id = :cid
          AND o.created_at >= :df AND o.created_at <= :dt
          AND o.status = 'delivered'
          {extra}
    """), params)).first()

    revenue = float(row.revenue or 0)
    ad_spend = float(row.ad_spend or 0)
    orders = float(orders_row.orders or 0)
    aov = float(orders_row.aov or 0)

    return {
        "revenue": revenue,
        "ad_spend": ad_spend,
        "commission": float(row.commission or 0),
        "logistics": float(row.logistics or 0),
        "acquiring": float(row.acquiring or 0),
        "orders": orders,
        "aov": aov,  # средний чек
        "drr_pct": (ad_spend / revenue * 100) if revenue > 0 else 0.0,
        "gross_profit": revenue - float(row.commission or 0) - float(row.logistics or 0)
                        - float(row.acquiring or 0) - ad_spend,
    }


async def simulate_plan_change(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    metric: str,
    delta: float,
    period_start: date | None = None,
    period_end: date | None = None,
    cabinet_id: uuid.UUID | None = None,
) -> CascadeResult:
    """
    Симуляция: +delta к метрике → каскад остальных.

    Поддерживаемые метрики:
      clicks       — клики (требует Performance API данных, упрощённо)
      ad_spend     — рекламный бюджет
      orders       — заказы
      revenue      — выручка (через прирост заказов)
      conversion_pct — конверсия (% корзина→заказ)
    """
    if period_end is None:
        period_end = date.today()
    if period_start is None:
        period_start = period_end - timedelta(days=30)

    base = await _get_base_metrics(
        db, company_id=company_id, period_start=period_start, period_end=period_end,
        cabinet_id=cabinet_id,
    )

    effects: list[CascadeEffect] = []
    cpc_be = None
    drr_after = base["drr_pct"]

    if metric == "ad_spend":
        # +ad → +clicks → +orders. Простая модель: на каждый ₽ +X заказов.
        # Базовый CPC и conversion из истории. CPO = ad_spend / orders.
        cpo = base["ad_spend"] / base["orders"] if base["orders"] > 0 else 0
        if cpo > 0:
            new_orders = delta / cpo
            new_revenue = new_orders * base["aov"]
            effects.append(CascadeEffect(
                metric="orders", delta=new_orders, new_value=base["orders"] + new_orders,
                explanation=f"+{delta:.0f}₽ × {1/cpo:.4f} заказ/₽ = +{new_orders:.0f} заказов",
            ))
            effects.append(CascadeEffect(
                metric="revenue", delta=new_revenue, new_value=base["revenue"] + new_revenue,
                explanation=f"+{new_orders:.0f} заказов × {base['aov']:.0f}₽ AOV = +{new_revenue:.0f}₽",
            ))
            drr_after = (base["ad_spend"] + delta) / (base["revenue"] + new_revenue) * 100
            margin_delta = new_revenue * 0.4 - delta  # ~40% маржинальности
            effects.append(CascadeEffect(
                metric="margin", delta=margin_delta, new_value=None,
                explanation=f"Прирост маржи (40% от {new_revenue:.0f}₽) − рекл.расход {delta:.0f}₽ = {margin_delta:+.0f}₽",
            ))
            cpc_be = base["aov"] * 0.4  # break-even CPO при 40% марже
    elif metric == "orders":
        # +orders → +revenue (через AOV)
        new_revenue = delta * base["aov"]
        effects.append(CascadeEffect(
            metric="revenue", delta=new_revenue, new_value=base["revenue"] + new_revenue,
            explanation=f"+{delta:.0f} заказов × {base['aov']:.0f}₽ AOV = +{new_revenue:.0f}₽",
        ))
        margin_delta = new_revenue * 0.4
        effects.append(CascadeEffect(
            metric="margin", delta=margin_delta, new_value=None,
            explanation=f"40% маржинальности × {new_revenue:.0f}₽ = +{margin_delta:.0f}₽",
        ))
        drr_after = base["ad_spend"] / (base["revenue"] + new_revenue) * 100
    elif metric == "revenue":
        # +revenue → пропорциональный прирост заказов
        if base["aov"] > 0:
            new_orders = delta / base["aov"]
            effects.append(CascadeEffect(
                metric="orders", delta=new_orders, new_value=base["orders"] + new_orders,
                explanation=f"+{delta:.0f}₽ / {base['aov']:.0f}₽ AOV = +{new_orders:.0f} заказов",
            ))
        margin_delta = delta * 0.4
        effects.append(CascadeEffect(
            metric="margin", delta=margin_delta, new_value=None,
            explanation=f"40% маржинальности × {delta:.0f}₽ = +{margin_delta:.0f}₽",
        ))
        drr_after = base["ad_spend"] / (base["revenue"] + delta) * 100
    elif metric == "clicks":
        # Упрощённо: считаем что 1 клик = 0.05 заказов (5% конверсия в корзину→заказ)
        conv = 0.05
        new_orders = delta * conv
        new_revenue = new_orders * base["aov"]
        effects.append(CascadeEffect(
            metric="orders", delta=new_orders, new_value=base["orders"] + new_orders,
            explanation=f"+{delta:.0f} кликов × {conv*100:.1f}% конверсия = +{new_orders:.0f} заказов",
        ))
        effects.append(CascadeEffect(
            metric="revenue", delta=new_revenue, new_value=base["revenue"] + new_revenue,
            explanation=f"+{new_orders:.0f} заказов × {base['aov']:.0f}₽ AOV = +{new_revenue:.0f}₽",
        ))
        # CPC break-even = (AOV × маржа%) / 1_клик_в_заказы = (AOV × 0.4) / 0.05
        cpc_be = (base["aov"] * 0.4 * conv) if conv > 0 else None

    return CascadeResult(
        input_metric=metric,
        input_delta=delta,
        base_period=(period_start, period_end),
        effects=effects,
        cpc_breakeven=cpc_be,
        drr_before_pct=round(base["drr_pct"], 2),
        drr_after_pct=round(drr_after, 2),
        note=(
            "Каскад использует средние коэффициенты из истории компании за период. "
            "Маржинальность принята 40% (можно уточнить через /finance/margin). "
            "Для точного расчёта эластичностей — /whatif на конкретный SKU."
        ),
    )
