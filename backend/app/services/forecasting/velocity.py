"""
Скорость продаж — два горизонта + сезонность + сигнал тренда.

ВАЖНО: это заглушка. Реальный расчёт смотрит на orders + stocks + market_trends_daily,
исключает дни в стокауте, применяет сезонность по категории, балансирует
longterm vs shortterm по выбранной стратегии.

ПРИНЦИП:
- avg_daily = total_units_sold / days_in_stock  (не календарные дни!)
- longterm = годовой средний × seasonal_factor_от_рынка_наперёд
- shortterm = weighted-average последних 30 дней (см. ForecastDefaults)
- trend_ratio = short / longterm
- recommended_daily — балансировка longterm/shortterm по стратегии
- confidence: low если данных меньше N дней или high CV
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.forecasting import ForecastDefaults


@dataclass
class VelocityResult:
    longterm_avg_daily: float
    longterm_seasonal_factor: float
    longterm_adjusted_daily: float
    longterm_confidence: str

    shortterm_avg_daily: float

    trend_ratio: float | None
    trend_signal: str

    recommended_daily: float
    recommendation_basis: str

    total_units_sold: int
    days_in_stock: int
    days_out_of_stock: int


def calculate_velocity(
    *,
    sales_by_day: dict,                    # {date: units_sold}
    in_stock_days: set,                    # {date} — дни когда был остаток
    longterm_window_days: int = 365,
    shortterm_window_days: int = 14,
    seasonal_index_ahead: float | None = None,  # из market_trends_daily
    forecast_strategy: str = "balanced",
) -> VelocityResult:
    """ЗАГЛУШКА. Возвращает структуру с разумными дефолтами.

    Реальный расчёт — TODO. Сейчас отдаёт всё нулями, чтобы пайплайн
    SalesVelocityCache мог записать строку и UI её показал.
    """
    # TODO: реальная логика
    return VelocityResult(
        longterm_avg_daily=0.0,
        longterm_seasonal_factor=seasonal_index_ahead or 1.0,
        longterm_adjusted_daily=0.0,
        longterm_confidence="low",
        shortterm_avg_daily=0.0,
        trend_ratio=None,
        trend_signal="stable",
        recommended_daily=0.0,
        recommendation_basis="placeholder — расчёт пока не реализован",
        total_units_sold=0,
        days_in_stock=len(in_stock_days),
        days_out_of_stock=0,
    )
