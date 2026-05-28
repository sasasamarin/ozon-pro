"""
Unit-экономика: ROI и ROMI — пункты 5 + 9.

ROI (Return on Investment) — отдача на ВЛОЖЕННЫЙ КАПИТАЛ (не маржа).
    ROI = profit / invested_capital

invested_capital = себестоимость товаров на складе + предоплаты поставщикам
                 + расходы, не отбившиеся ещё (например, заплаченный налог).

ROMI (Return on Marketing Investment) — отдача рекламы.
    Наш ВАРИАНТ (исправление nepsell): ROMI считаем от ВАЛОВОЙ МАРЖИ заказа,
    а не от чистой прибыли. Общие OPEX (зарплаты, аренда) — это маржинальное
    решение бизнеса, нельзя вешать на отдельную кампанию.

    ROMI = gross_margin_from_ad_orders / ad_spend × 100%

    Плюс показываем ДРР (привычный ориентир):
    ДРР = ad_spend / revenue_from_ad_orders × 100%

    gross_margin_per_order = price − cost − commission − logistics
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.forecasting import ForecastConfidence


@dataclass
class ROIResult:
    roi_pct: float
    period_days: int
    profit_rub: float
    capital_rub: float
    confidence: str
    basis: str


def calc_roi(
    *,
    profit_rub: float,
    invested_capital_rub: float,
    period_days: int = 30,
) -> ROIResult:
    """ROI = profit / capital. Возвращает в процентах.

    Если capital <= 0 — None ROI, confidence=low.
    """
    if invested_capital_rub <= 0:
        return ROIResult(
            roi_pct=0.0,
            period_days=period_days,
            profit_rub=profit_rub,
            capital_rub=invested_capital_rub,
            confidence=ForecastConfidence.LOW.value,
            basis="вложенный капитал = 0 — ROI не определён",
        )

    roi = (profit_rub / invested_capital_rub) * 100.0
    conf = (
        ForecastConfidence.HIGH.value if period_days >= 30 else ForecastConfidence.MEDIUM.value
    )
    return ROIResult(
        roi_pct=round(roi, 2),
        period_days=period_days,
        profit_rub=profit_rub,
        capital_rub=invested_capital_rub,
        confidence=conf,
        basis=(
            f"{profit_rub:.0f}₽ прибыли / {invested_capital_rub:.0f}₽ вложенного "
            f"капитала за {period_days} дней"
        ),
    )


@dataclass
class GrossMarginUnit:
    """Валовая маржа одной единицы заказа (на которой строится ROMI)."""

    price: float
    cost: float
    commission: float
    logistics: float
    gross_margin: float  # price − cost − commission − logistics


def calc_gross_margin_unit(
    *,
    price: float,
    cost: float,
    commission: float,
    logistics: float = 0.0,
) -> GrossMarginUnit:
    gross = price - cost - commission - logistics
    return GrossMarginUnit(
        price=price,
        cost=cost,
        commission=commission,
        logistics=logistics,
        gross_margin=round(gross, 2),
    )


@dataclass
class ROMIResult:
    romi_pct: float            # ROMI от валовой маржи
    drr_pct: float             # ДРР как привычный ориентир
    ad_spend_rub: float
    revenue_from_ads_rub: float
    gross_margin_from_ads_rub: float
    orders_count: int
    confidence: str
    basis: str


def calc_romi_from_gross(
    *,
    ad_spend_rub: float,
    revenue_from_ads_rub: float,
    gross_margin_from_ads_rub: float,
    orders_count: int,
) -> ROMIResult:
    """ROMI от ВАЛОВОЙ маржи, плюс ДРР как привычный ориентир.

    Пункт 9: nepsell считает ROMI от ЧИСТОЙ — это ошибка для уровня кампании.
    Общие OPEX не зависят от того, идёт ли реклама конкретного товара. Поэтому
    ROMI считаем от валовой маржи. Чистая прибыль — только на уровне P&L бизнеса.
    """
    if ad_spend_rub <= 0:
        return ROMIResult(
            romi_pct=0.0,
            drr_pct=0.0,
            ad_spend_rub=0.0,
            revenue_from_ads_rub=revenue_from_ads_rub,
            gross_margin_from_ads_rub=gross_margin_from_ads_rub,
            orders_count=orders_count,
            confidence=ForecastConfidence.LOW.value,
            basis="ad_spend = 0 — ROMI/ДРР не считаются",
        )

    romi = (gross_margin_from_ads_rub / ad_spend_rub) * 100.0
    drr = (
        (ad_spend_rub / revenue_from_ads_rub) * 100.0 if revenue_from_ads_rub > 0 else 0.0
    )

    if orders_count >= 50:
        conf = ForecastConfidence.HIGH.value
    elif orders_count >= 10:
        conf = ForecastConfidence.MEDIUM.value
    else:
        conf = ForecastConfidence.LOW.value

    return ROMIResult(
        romi_pct=round(romi, 2),
        drr_pct=round(drr, 2),
        ad_spend_rub=ad_spend_rub,
        revenue_from_ads_rub=revenue_from_ads_rub,
        gross_margin_from_ads_rub=gross_margin_from_ads_rub,
        orders_count=orders_count,
        confidence=conf,
        basis=(
            f"{orders_count} заказов от рекламы: валовая {gross_margin_from_ads_rub:.0f}₽ / "
            f"расход {ad_spend_rub:.0f}₽ = ROMI {romi:.1f}%. "
            f"ДРР {drr:.1f}% (расход/выручка)"
        ),
    )
