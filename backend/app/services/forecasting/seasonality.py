"""
Сезонность — пункт 10 (наше исправление nepsell).

У них только категорийная сезонность. У нас гибридный подход:

    seasonal_index = (1 − w) × category_index + w × own_yoy_index

где `w` — вес собственной истории, растёт от 0 до OWN_HISTORY_MAX_WEIGHT (0.7)
по мере накопления своей истории. Категорийный индекс — БАЗА (от рынка через
market_trends_daily), своя история — КОРРЕКТИРОВКА.

Своя YoY-история: берём 8 завершённых недель с отступом 4 недели назад
(плато-период, не текущая шумная неделя). Год к году — соотношение к тем же
неделям прошлого года.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.forecasting import ForecastConfidence, ForecastDefaults


@dataclass
class SeasonalityResult:
    seasonal_index: float          # >1.0 = высокий сезон, <1.0 = низкий
    confidence: str
    category_index: float | None   # из market_trends_daily
    own_yoy_index: float | None    # из собственной истории
    own_weight: float              # сколько веса дали своей истории (0..0.7)
    days_of_own_history: int       # для прозрачности
    basis: str


def calc_own_history_weight(days_of_history: int) -> float:
    """Вес собственной истории растёт линейно от MIN до FULL по дням.

    0 при < 30 дней, плавно до 0.7 при >= 365 дней.
    """
    if days_of_history <= ForecastDefaults.OWN_HISTORY_MIN_DAYS:
        return 0.0
    if days_of_history >= ForecastDefaults.OWN_HISTORY_FULL_DAYS:
        return ForecastDefaults.OWN_HISTORY_MAX_WEIGHT
    # Линейная интерполяция
    ratio = (
        (days_of_history - ForecastDefaults.OWN_HISTORY_MIN_DAYS)
        / (ForecastDefaults.OWN_HISTORY_FULL_DAYS - ForecastDefaults.OWN_HISTORY_MIN_DAYS)
    )
    return ratio * ForecastDefaults.OWN_HISTORY_MAX_WEIGHT


def combined_seasonal_factor(
    *,
    category_index: float | None,
    own_yoy_index: float | None,
    days_of_own_history: int,
) -> SeasonalityResult:
    """Гибридная сезонность: категория-база + своя история по весу.

    - Только категорийный есть → возвращаем его с confidence=medium
    - Только своя есть → confidence=low (не было категорийных данных), используем
    - Оба есть → взвешенная сумма, confidence=high если >= 365 дней истории
    - Ничего нет → 1.0 (нейтральная), confidence=low
    """
    if category_index is None and own_yoy_index is None:
        return SeasonalityResult(
            seasonal_index=1.0,
            confidence=ForecastConfidence.LOW.value,
            category_index=None,
            own_yoy_index=None,
            own_weight=0.0,
            days_of_own_history=days_of_own_history,
            basis="нет ни категорийной, ни собственной сезонности — нейтральный 1.0",
        )

    if own_yoy_index is None or category_index is None:
        # Только один источник
        if own_yoy_index is None:
            return SeasonalityResult(
                seasonal_index=category_index or 1.0,
                confidence=ForecastConfidence.MEDIUM.value,
                category_index=category_index,
                own_yoy_index=None,
                own_weight=0.0,
                days_of_own_history=days_of_own_history,
                basis=f"только категорийный индекс {category_index:.2f}",
            )
        return SeasonalityResult(
            seasonal_index=own_yoy_index,
            confidence=ForecastConfidence.LOW.value,
            category_index=None,
            own_yoy_index=own_yoy_index,
            own_weight=1.0,
            days_of_own_history=days_of_own_history,
            basis=f"только своя YoY-история {own_yoy_index:.2f} (нет market-данных)",
        )

    # Оба источника есть — взвешиваем
    w = calc_own_history_weight(days_of_own_history)
    combined = (1.0 - w) * category_index + w * own_yoy_index

    if days_of_own_history >= ForecastDefaults.OWN_HISTORY_FULL_DAYS:
        conf = ForecastConfidence.HIGH.value
    elif days_of_own_history >= 90:
        conf = ForecastConfidence.MEDIUM.value
    else:
        conf = ForecastConfidence.LOW.value

    return SeasonalityResult(
        seasonal_index=combined,
        confidence=conf,
        category_index=category_index,
        own_yoy_index=own_yoy_index,
        own_weight=w,
        days_of_own_history=days_of_own_history,
        basis=(
            f"{(1 - w) * 100:.0f}% категория ({category_index:.2f}) + "
            f"{w * 100:.0f}% YoY ({own_yoy_index:.2f}) = {combined:.2f}"
        ),
    )
