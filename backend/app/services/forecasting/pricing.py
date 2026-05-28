"""
Обратный расчёт цены от требуемой рентабельности — пункт 4 (nepsell-канон).

Стандартный подход «прибыль при цене X» инвертирован:
    Вход: целевая рентабельность (%) + все издержки за единицу
    Выход: цена, при которой эта рентабельность достигается

Формула:
    price = (cost + commission_fixed + logistics + ad_spend_per_unit + other) /
            (1 − target_margin_pct / 100 − commission_percent_of_price / 100)

(Учитываем что комиссия Ozon обычно % от цены, а не fixed → формула с
переменной в знаменателе.)

Если знаменатель ≤ 0 (цель слишком высокая для текущих комиссий) → возвращаем
None + объяснение, какая максимально возможная маржа.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.forecasting import ForecastConfidence, ForecastDefaults


@dataclass
class ReversePriceResult:
    target_margin_pct: float
    suggested_price: float | None        # None если не достижимо
    max_achievable_margin_pct: float     # потолок при текущих условиях
    breakdown: dict[str, float]          # подробности для UI
    confidence: str                      # high если все 4 поля заполнены
    basis: str


def reverse_price_from_target_margin(
    *,
    target_margin_pct: float,
    cost_per_unit: float,
    fixed_costs_per_unit: float = 0.0,
    commission_percent_of_price: float = 0.0,
    delivery_per_unit: float = 0.0,
    ad_spend_per_unit: float = 0.0,
) -> ReversePriceResult:
    """Цена для достижения целевой валовой маржи.

    Все вход-параметры — в рублях/процентах за ОДНУ ЕДИНИЦУ товара.

    - cost_per_unit: себестоимость
    - fixed_costs_per_unit: упаковка / разовая комиссия Ozon / прочее фиксированное
    - commission_percent_of_price: % комиссии Ozon (зависит от категории)
    - delivery_per_unit: логистика на одну единицу
    - ad_spend_per_unit: распределённая на единицу рекламная нагрузка
    """
    fixed_total = (
        cost_per_unit + fixed_costs_per_unit + delivery_per_unit + ad_spend_per_unit
    )

    # price × (1 − margin% − commission_percent%) = fixed_total
    denom = 1.0 - (target_margin_pct / 100.0) - (commission_percent_of_price / 100.0)

    if denom <= 0:
        # Целевая маржа недостижима — комиссия + цель ≥ 100%
        max_margin = (1.0 - commission_percent_of_price / 100.0) * 100.0
        return ReversePriceResult(
            target_margin_pct=target_margin_pct,
            suggested_price=None,
            max_achievable_margin_pct=max(0.0, max_margin),
            breakdown={
                "cost_per_unit": cost_per_unit,
                "fixed_costs_per_unit": fixed_costs_per_unit,
                "delivery_per_unit": delivery_per_unit,
                "ad_spend_per_unit": ad_spend_per_unit,
                "commission_percent_of_price": commission_percent_of_price,
            },
            confidence=ForecastConfidence.HIGH.value,
            basis=(
                f"целевая маржа {target_margin_pct}% + комиссия "
                f"{commission_percent_of_price}% превышают 100%"
            ),
        )

    suggested = fixed_total / denom

    # Confidence по полноте входов
    enabled = sum(1 for v in (cost_per_unit, commission_percent_of_price) if v > 0)
    if cost_per_unit > 0 and commission_percent_of_price > 0:
        conf = ForecastConfidence.HIGH.value
    elif cost_per_unit > 0:
        conf = ForecastConfidence.MEDIUM.value
    else:
        conf = ForecastConfidence.LOW.value

    return ReversePriceResult(
        target_margin_pct=target_margin_pct,
        suggested_price=round(suggested, 2),
        max_achievable_margin_pct=(1.0 - commission_percent_of_price / 100.0) * 100.0,
        breakdown={
            "cost_per_unit": cost_per_unit,
            "fixed_costs_per_unit": fixed_costs_per_unit,
            "delivery_per_unit": delivery_per_unit,
            "ad_spend_per_unit": ad_spend_per_unit,
            "commission_percent_of_price": commission_percent_of_price,
        },
        confidence=conf,
        basis=(
            f"цена = ({fixed_total:.2f}) / (1 − {target_margin_pct}% − "
            f"{commission_percent_of_price}%) = {suggested:.2f}"
        ),
    )
