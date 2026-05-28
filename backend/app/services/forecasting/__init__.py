"""
Forecasting и unit-economics движок Flowoi.

Структура (точно копирует обкатанный у nepsell flow за 2 года / 100+ млн ₽
оборота, плюс наши уточнения в ROMI и сезонности):

- buyout.py        — выкупаемость (доставлено − возвраты) / все_доехавшие за 90 дней
- velocity.py      — скорость продаж + мультипликатор «дни в наличии»
- seasonality.py   — категория (market_trends_daily) + своя история YoY с весом
- abc.py           — 3-осевой ABC: выручка / валовая / чистая прибыль
- pricing.py       — обратный расчёт цены от требуемой рентабельности %
- unit_economics.py — ROMI (от ВАЛОВОЙ маржи) + ROI (отдача на капитал)
- whatif.py        — симулятор «что изменится в прибыли» при смене цены/ставки
- procurement.py   — рекомендация закупок (когда + сколько) — использует buyout + velocity

ПРИНЦИП КОЭФФИЦИЕНТОВ:
Все коэффициенты — заглушки в ForecastDefaults. Реальные тюним после накопления
проверочной истории по фактическим продажам (с 2025-01-01 синхронизировано
~30к заказов + ~85к транзакций). Confidence-метка пишется ВСЕГДА.

ПРИНЦИП CONFIDENCE:
- high   — >= 90 дней истории + days_in_stock >= 60% + low CV
- medium — 30-90 дней истории или days_in_stock 30-60%
- low    — < 30 дней истории, days_in_stock < 30%, high CV или ≤3 дня в наличии

ПРИНЦИП FAIL-SAFE:
Любая формула, не уверенная в данных → confidence=low + recommendation_basis
объясняет почему. UI должен показывать confidence в каждой рекомендации, чтобы
пользователь понимал почему агрессивная рекомендация не даётся.
"""
from __future__ import annotations

from enum import Enum


class ForecastConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ForecastDefaults:
    """Коэффициенты — настраиваем когда накопим валидационную историю."""

    # === BUYOUT (пункт 1) ===
    BUYOUT_WINDOW_DAYS = 90
    # Если buyout не считается (< 30 заказов в окне) — берём дефолт «осторожный»
    BUYOUT_FALLBACK_RATE = 0.60  # 60% — типичная нижняя граница для бытовой техники / стройматериалов

    # === DAYS-IN-STOCK MULTIPLIER (пункт 2) ===
    DAYS_IN_STOCK_WINDOW = 28
    # Кривая: при пропорции дней-в-наличии к окну
    MULTIPLIER_FULL = 1.0           # >= 27/28 дней (≈100%) → ×1
    MULTIPLIER_TWO_THIRDS = 1.3     # 21/28 → ×1.3
    MULTIPLIER_HALF = 2.0           # 14/28 → ×2.0
    MULTIPLIER_MAX = 3.0            # ≤8/28 → ×3 (НЕ больше — пункт 2)
    # Безопасность: ≤3 дней в наличии → confidence=low независимо от множителя
    MIN_DAYS_IN_STOCK_FOR_CONFIDENCE = 3

    # === ABC (пункт 3) ===
    # Стандартные пороги Парето
    ABC_A_THRESHOLD = 0.80  # верхние 80% накопленных
    ABC_B_THRESHOLD = 0.95  # дальше до 95%
    # C — остаток (5%)

    # === ROI / ROMI / margin (пункт 5 + 9) ===
    # ROMI считаем от ВАЛОВОЙ маржи заказа (цена − себестоимость − комиссия − логистика),
    # НЕ от чистой прибыли. Общие OPEX (зарплаты/аренда) на уровень кампании не вешаем.
    ROMI_FROM_GROSS_MARGIN = True

    # === SEASONALITY (пункт 10) ===
    # Гибридный подход:
    # - market_trends_daily.seasonal_index (по категории) — БАЗА
    # - своя YoY-история — КОРРЕКТИРОВКА с весом по надёжности
    # Вес собственной истории: 0 при < 30 дней истории, плавно растёт до 0.7
    # при >= 365 дней (учитываем 1 полный сезон).
    OWN_HISTORY_MAX_WEIGHT = 0.7
    OWN_HISTORY_MIN_DAYS = 30
    OWN_HISTORY_FULL_DAYS = 365
    # YoY: 8 завершённых недель с отступом 4 недели назад (стабильный плато-период)
    YOY_WEEKS_OFFSET = 4
    YOY_WEEKS_COUNT = 8

    # === Forecast windows ===
    SHORTTERM_WEIGHTS = (
        (range(0, 7), 0.50),
        (range(7, 14), 0.30),
        (range(14, 30), 0.20),
    )
    TREND_RISING = 1.20
    TREND_FALLING = 0.80
    VOLATILE_CV = 0.50

    MIN_DAYS_FOR_HIGH_CONFIDENCE = 30
    MIN_DAYS_IN_STOCK_FOR_VELOCITY = 7

    REVIEW_PERIOD_DAYS = 7


__all__ = ["ForecastConfidence", "ForecastDefaults"]
