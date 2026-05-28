"""
Рекомендация закупок: КОГДА и СКОЛЬКО заказать. Интегрирует velocity + buyout.

Формула:
    days_left = (current_stock + in_transit_from_supplier
                + projected_returning_stock × (1 − buyout)) / recommended_daily
    reorder_point = lead_time_total_days + safety_stock_days
    need_reorder  = days_left <= reorder_point
    raw_need      = recommended_daily × (lead_time_total + review_period)
                    − in_transit_from_supplier
    recommended_qty:
        if raw_need < moq → moq
        elif batch_strict → ceil(raw_need / step) × step
        else             → max(raw_need, moq)

UX (вывод):
    расчётная потребность + ограничение поставщика (MOQ/кратность) + финальная
    рекомендация + «заказать до» + дата прогноз-стокаута + почему.

ПРИНЦИП: система ПОДСКАЗЫВАЕТ. Никаких автозаказов. UI показывает оба горизонта
(velocity longterm + shortterm), сигнал тренда, и confidence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from app.services.forecasting import ForecastConfidence, ForecastDefaults
from app.services.forecasting.buyout import BuyoutResult
from app.services.forecasting.velocity import VelocityResult


@dataclass
class ProcurementRecommendation:
    need_reorder: bool
    days_left: float
    raw_need: float                  # сколько надо без учёта MOQ/batch
    recommended_qty: int             # финальная цифра с учётом MOQ и кратности
    order_by: date | None            # последний день, когда ещё успеваешь
    projected_stockout: date | None  # когда закончится текущий запас

    confidence: str
    basis: str                       # объяснение для UI («почему такая рекомендация»)
    warnings: list[str]              # риски (overstock / cap из-за low confidence)


def recommend_procurement(
    *,
    today: date,
    current_stock: int,
    in_transit_from_supplier: int,
    in_transit_from_customer: int,
    velocity: VelocityResult,
    buyout: BuyoutResult,
    lead_time_total_days: int,
    safety_stock_days: int,
    moq: int,
    batch_step: int,
    batch_strict: bool,
    review_period_days: int = ForecastDefaults.REVIEW_PERIOD_DAYS,
) -> ProcurementRecommendation:
    """Главный вход. Объединяет velocity (с мультипликатором) + buyout."""
    warnings: list[str] = []

    daily = velocity.adjusted_daily
    if daily <= 0:
        return ProcurementRecommendation(
            need_reorder=False, days_left=float("inf"), raw_need=0.0,
            recommended_qty=0, order_by=None, projected_stockout=None,
            confidence=ForecastConfidence.LOW.value,
            basis="нет продаж в окне — рекомендация не даётся",
            warnings=[],
        )

    # «Вернётся на склад от клиентов» = (заказы в пути ОТ клиента) × (1 − buyout)
    returning_stock = in_transit_from_customer * (1 - buyout.rate)

    available = current_stock + in_transit_from_supplier + returning_stock
    days_left = available / daily
    reorder_point = lead_time_total_days + safety_stock_days
    need_reorder = days_left <= reorder_point

    raw_need = max(0.0, daily * (lead_time_total_days + review_period_days) - in_transit_from_supplier)

    if raw_need < moq:
        recommended_qty = moq
    elif batch_strict:
        recommended_qty = math.ceil(raw_need / batch_step) * batch_step
    else:
        recommended_qty = int(max(raw_need, moq))

    order_by = today + timedelta(days=max(0, int(days_left - lead_time_total_days)))
    projected_stockout = today + timedelta(days=int(days_left))

    # Confidence — берём минимум из velocity и buyout
    if velocity.confidence == ForecastConfidence.LOW.value or buyout.confidence == ForecastConfidence.LOW.value:
        conf = ForecastConfidence.LOW.value
        warnings.append("рекомендация консервативная — недостаточно данных")
    elif velocity.confidence == ForecastConfidence.HIGH.value and buyout.confidence == ForecastConfidence.HIGH.value:
        conf = ForecastConfidence.HIGH.value
    else:
        conf = ForecastConfidence.MEDIUM.value

    # Risk: overstock if days_left already very large
    if days_left > lead_time_total_days * 3:
        warnings.append(f"days_left={days_left:.0f} — overstock-риск, спросить нужна ли закупка")

    basis = (
        f"скорость {daily:.1f}/день (×{velocity.multiplier:.1f} от days-in-stock), "
        f"buyout {buyout.rate:.0%} ({buyout.confidence}), "
        f"available={available:.0f} → {days_left:.0f} дней. "
        f"reorder_point = lead_time {lead_time_total_days} + safety {safety_stock_days} = {reorder_point} дней. "
        f"need_reorder = {need_reorder}"
    )

    return ProcurementRecommendation(
        need_reorder=need_reorder,
        days_left=round(days_left, 1),
        raw_need=round(raw_need, 1),
        recommended_qty=recommended_qty,
        order_by=order_by,
        projected_stockout=projected_stockout,
        confidence=conf,
        basis=basis,
        warnings=warnings,
    )
