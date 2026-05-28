"""
Прогнозирование скорости продаж и закупок.

Структура (заглушки, коэффициенты-дефолты — менять без переписывания UI):
- DEFAULTS: коэффициенты-веса для расчёта recommended_daily
- velocity.py: скорость продаж (два горизонта + сезонность + тренд)
- procurement.py: рекомендация закупок (когда + сколько)

Принцип: система ПОДСКАЗЫВАЕТ. Никаких автозаказов. UI показывает оба горизонта,
сигнал тренда и «почему». Подробнее — в docstrings.
"""
from __future__ import annotations


class ForecastDefaults:
    """Дефолтные коэффициенты — меняются здесь, не пересобирая UI."""

    # Веса weighted-average для shortterm-горизонта по дням-от-сейчас
    # (последние 7 дн: 50%, дни 8-14: 30%, дни 15-30: 20%)
    SHORTTERM_WEIGHTS = (
        (range(0, 7), 0.50),
        (range(7, 14), 0.30),
        (range(14, 30), 0.20),
    )

    # Порог тренд-ratio для категоризации сигнала
    TREND_RISING = 1.20
    TREND_FALLING = 0.80
    # Высокая дисперсия → volatile (CV > 0.5)
    VOLATILE_CV = 0.50

    # Confidence-пороги
    MIN_DAYS_FOR_HIGH_CONFIDENCE = 30  # дней истории
    MIN_DAYS_IN_STOCK_FOR_VELOCITY = 7  # ниже → low confidence

    # Период «между перезаказами» по умолчанию
    REVIEW_PERIOD_DAYS = 7


__all__ = ["ForecastDefaults"]
