"""
Закупочная рекомендация: КОГДА и СКОЛЬКО заказать.

ВАЖНО: заглушка. Реальная логика:
- days_left = (current_stock + in_transit) / recommended_daily
- reorder_point = lead_time_total + safety_stock_days
- need_reorder = days_left <= reorder_point
- raw_need = recommended_daily × (lead_time_total + review_period) − in_transit
- recommended_qty: учитывает MOQ и batch_step (опционально strict-кратность)

UX-вывод: расчётная потребность + ограничение поставщика + финальная рекомендация
+ «заказать до даты» + дата прогноз-стокаута + почему.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.services.forecasting import ForecastDefaults


@dataclass
class ProcurementRecommendation:
    need_reorder: bool
    days_left: float
    raw_need: float                  # сколько надо без учёта MOQ/batch
    recommended_qty: int             # финальная цифра с учётом MOQ и кратности
    order_by: date | None            # последний день, когда ещё успеваешь
    projected_stockout: date | None  # когда закончится текущий запас
    basis: str                       # объяснение для UI


def recommend_procurement(
    *,
    today: date,
    current_stock: int,
    in_transit: int,
    recommended_daily: float,
    lead_time_total_days: int,
    safety_stock_days: int,
    moq: int,
    batch_step: int,
    batch_strict: bool,
    review_period_days: int = ForecastDefaults.REVIEW_PERIOD_DAYS,
) -> ProcurementRecommendation:
    """ЗАГЛУШКА. Возвращает безопасные дефолты.

    Реализация ожидается в Phase 2.5.
    """
    available = current_stock + in_transit
    days_left = (available / recommended_daily) if recommended_daily > 0 else float("inf")
    reorder_point = lead_time_total_days + safety_stock_days
    need_reorder = days_left <= reorder_point

    # raw_need грубо считаем чтобы UI хоть что-то показывал
    raw_need = max(
        0.0,
        recommended_daily * (lead_time_total_days + review_period_days) - in_transit,
    )

    if raw_need < moq:
        recommended_qty = moq
    elif batch_strict:
        import math
        recommended_qty = math.ceil(raw_need / batch_step) * batch_step
    else:
        recommended_qty = int(max(raw_need, moq))

    order_by = today + timedelta(days=int(days_left) - lead_time_total_days) if recommended_daily > 0 else None
    projected_stockout = today + timedelta(days=int(days_left)) if recommended_daily > 0 else None

    return ProcurementRecommendation(
        need_reorder=need_reorder,
        days_left=days_left,
        raw_need=raw_need,
        recommended_qty=recommended_qty,
        order_by=order_by,
        projected_stockout=projected_stockout,
        basis="placeholder — упрощённый расчёт, требует валидации",
    )
