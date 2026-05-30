"""
What-if симулятор — пункт 6 (nepsell-канон).

«Что изменится в прибыли, если...?» — пересчёт на фактических заказах × выкупаемости,
ПОКАЗЫВАЕМ ДО ДЕЙСТВИЯ. Цель — снизить количество слепых правок цен/ставок.

Сценарии:
- simulate_price_change(new_price) → новая прибыль, новая эластичная конверсия
  (TODO: эластичность — отдельная модель, пока берём наивно сохранение объёма)
- simulate_ad_bid_change(new_bid) → новый CTR, новые заказы, новая ROMI
  (TODO: эластичность ставки — модель аукциона Ozon, пока линейная)

Сейчас — структура и dummy-формулы. Реальная эластичность реализуется когда
будет 90+ дней А/B-данных по ценам/ставкам.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.forecasting import ForecastConfidence
from app.services.forecasting.unit_economics import calc_gross_margin_unit


@dataclass
class WhatIfPriceResult:
    selling_price: float              # рабочая цена продавца (marketing_seller_price, не зачёркнутая)
    new_price: float
    delta_price_pct: float

    estimated_new_orders: float       # с поправкой на эластичность (заглушка: same)
    estimated_revenue_change: float
    estimated_gross_margin_change: float

    confidence: str
    basis: str
    warnings: list[str]               # «риски» (упасть ниже min_price и т.д.)


def simulate_price_change(
    *,
    selling_price: float,
    new_price: float,
    avg_daily_orders: float,
    horizon_days: int = 30,
    cost_per_unit: float = 0.0,
    commission_pct: float = 0.0,
    logistics_per_unit: float = 0.0,
    min_price: float | None = None,
) -> WhatIfPriceResult:
    """Прибыль/выручка при новой цене.

    selling_price = marketing_seller_price (рабочая цена продавца, от неё accruals и комиссия).
    Зачёркнутая «до скидки» (Ozon `price`) в расчётах НЕ участвует.

    ЗАГЛУШКА: эластичность спроса по цене НЕ моделируется (TODO).
    Сейчас наивно: объём заказов остаётся прежним.
    """
    delta_pct = ((new_price - selling_price) / max(selling_price, 1)) * 100.0
    units = avg_daily_orders * horizon_days

    cur_gross = calc_gross_margin_unit(
        price=selling_price,
        cost=cost_per_unit,
        commission=selling_price * commission_pct / 100,
        logistics=logistics_per_unit,
    ).gross_margin
    new_gross = calc_gross_margin_unit(
        price=new_price,
        cost=cost_per_unit,
        commission=new_price * commission_pct / 100,
        logistics=logistics_per_unit,
    ).gross_margin

    revenue_change = (new_price - selling_price) * units
    gross_change = (new_gross - cur_gross) * units

    warnings: list[str] = []
    if min_price is not None and new_price < min_price:
        warnings.append(f"new_price={new_price} ниже min_price={min_price} — может попасть в bonus")
    if new_gross < 0:
        warnings.append("новая валовая маржа отрицательна — продаёшь в минус")

    return WhatIfPriceResult(
        selling_price=selling_price,
        new_price=new_price,
        delta_price_pct=round(delta_pct, 2),
        estimated_new_orders=units,
        estimated_revenue_change=round(revenue_change, 2),
        estimated_gross_margin_change=round(gross_change, 2),
        confidence=ForecastConfidence.LOW.value,
        basis=(
            "наивно: объём заказов сохраняется. Эластичность по цене — TODO "
            "(нужно 90+ дней истории по этому SKU с разными ценами)"
        ),
        warnings=warnings,
    )


@dataclass
class WhatIfBidResult:
    current_bid: float
    new_bid: float
    delta_bid_pct: float

    estimated_new_clicks: float
    estimated_new_orders: float
    estimated_new_romi_pct: float
    estimated_new_drr_pct: float

    confidence: str
    basis: str
    warnings: list[str]


def simulate_ad_bid_change(
    *,
    current_bid: float,
    new_bid: float,
    current_clicks: float,
    current_orders: float,
    revenue_per_order: float,
    gross_margin_per_order: float,
    horizon_days: int = 30,
) -> WhatIfBidResult:
    """ROMI/ДРР при изменении ставки рекламы.

    ЗАГЛУШКА: эластичность ставки в аукционе Ozon линейная (нереалистично, но
    даёт UI работать). Реальная модель — отдельная задача.
    """
    delta_pct = ((new_bid - current_bid) / max(current_bid, 0.01)) * 100.0
    # Линейная: ×(new/current) — на самом деле логарифмическая или ступенчатая
    multiplier = new_bid / max(current_bid, 0.01)
    new_clicks = current_clicks * multiplier
    new_orders = current_orders * multiplier  # CR не меняется
    new_revenue = new_orders * revenue_per_order
    new_gross = new_orders * gross_margin_per_order
    new_ad_spend = new_bid * new_clicks * horizon_days  # очень грубо

    romi = (new_gross / new_ad_spend * 100) if new_ad_spend > 0 else 0
    drr = (new_ad_spend / new_revenue * 100) if new_revenue > 0 else 0

    warnings: list[str] = []
    if drr > 50:
        warnings.append(f"ДРР {drr:.0f}% > 50% — реклама съест маржу")

    return WhatIfBidResult(
        current_bid=current_bid,
        new_bid=new_bid,
        delta_bid_pct=round(delta_pct, 2),
        estimated_new_clicks=round(new_clicks, 1),
        estimated_new_orders=round(new_orders, 1),
        estimated_new_romi_pct=round(romi, 1),
        estimated_new_drr_pct=round(drr, 1),
        confidence=ForecastConfidence.LOW.value,
        basis=(
            "линейная эластичность ставки — заглушка. Реальная модель аукциона "
            "Ozon (логарифмическая, ступенчатая) — отдельная задача."
        ),
        warnings=warnings,
    )
