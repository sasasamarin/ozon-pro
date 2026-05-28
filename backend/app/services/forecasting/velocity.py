"""
Скорость продаж + days-in-stock multiplier — пункт 2.

Идея: товар, который продавался N штук в день, будучи в наличии только 14 из 28
дней окна, в реальности продал бы ×2 больше при 100% наличии. Это даёт
«истинную» velocity, на которой строятся прогнозы и закупки.

Кривая мультипликатора (nepsell-канон):
    days_in_stock / window:
       ~100%  →  ×1
       21/28  →  ×1.3
       14/28  →  ×2.0
       ≤8/28  →  ×3 (ПОТОЛОК — не больше, иначе агрессивный over-stock)

Наше дополнение (исправление спорного места):
    ≤ MIN_DAYS_IN_STOCK_FOR_CONFIDENCE (3 дня) → confidence=LOW + флаг
    «недостаточно данных для агрессивной рекомендации». Множитель остаётся ×3,
    но в UI/в procurement используется консервативно.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.forecasting import ForecastConfidence, ForecastDefaults


@dataclass
class VelocityResult:
    raw_avg_daily: float          # sold_units / days_in_stock (без корректировки)
    multiplier: float             # 1.0…3.0
    adjusted_daily: float         # raw * multiplier
    confidence: str
    days_in_stock: int
    days_out_of_stock: int
    window_days: int
    total_units_sold: int
    basis: str                    # объяснение для UI


def calc_days_in_stock_multiplier(days_in_stock: int, window: int) -> float:
    """Кусочно-линейный мультипликатор по таблице ForecastDefaults.

    Возвращает значение в [1.0, MULTIPLIER_MAX]. Кривая:
        100% → 1.0
        21/28 (≈75%) → 1.3
        14/28 (50%) → 2.0
        8/28  (~29%) → 3.0
        ≤8/28 → cap 3.0
    """
    if window <= 0:
        return ForecastDefaults.MULTIPLIER_MAX
    ratio = days_in_stock / window
    if ratio >= (27 / 28):
        return ForecastDefaults.MULTIPLIER_FULL
    if ratio >= (21 / 28):
        # 21..27 → 1.0..1.3 (линейная интерполяция)
        return _lerp(
            ratio, (21 / 28), (27 / 28),
            ForecastDefaults.MULTIPLIER_TWO_THIRDS, ForecastDefaults.MULTIPLIER_FULL,
        )
    if ratio >= (14 / 28):
        # 14..21 → 2.0..1.3
        return _lerp(
            ratio, (14 / 28), (21 / 28),
            ForecastDefaults.MULTIPLIER_HALF, ForecastDefaults.MULTIPLIER_TWO_THIRDS,
        )
    if ratio >= (8 / 28):
        # 8..14 → 3.0..2.0
        return _lerp(
            ratio, (8 / 28), (14 / 28),
            ForecastDefaults.MULTIPLIER_MAX, ForecastDefaults.MULTIPLIER_HALF,
        )
    return ForecastDefaults.MULTIPLIER_MAX


def _lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    if x1 == x0:
        return y0
    t = (x - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


def calc_velocity(
    *,
    total_units_sold: int,
    days_in_stock: int,
    days_out_of_stock: int,
    window: int = ForecastDefaults.DAYS_IN_STOCK_WINDOW,
) -> VelocityResult:
    """Скорость продаж с поправкой на дни-в-наличии.

    raw_avg_daily = total_units_sold / max(days_in_stock, 1)  ← НЕ календарные!
    multiplier    = функция от ratio = days_in_stock / window
    adjusted      = raw × multiplier

    Confidence:
    - LOW    если days_in_stock <= 3 (слишком мало, чтобы быть уверенным)
    - LOW    если total_units_sold < 5 (статистически шум)
    - MEDIUM иначе при days_in_stock < window
    - HIGH   при ratio >= 0.95
    """
    days_in_stock = max(0, days_in_stock)
    days_out_of_stock = max(0, days_out_of_stock)
    safe_dis = max(days_in_stock, 1)
    raw = total_units_sold / safe_dis

    mult = calc_days_in_stock_multiplier(days_in_stock, window)
    adjusted = raw * mult

    # Confidence
    if days_in_stock <= ForecastDefaults.MIN_DAYS_IN_STOCK_FOR_CONFIDENCE:
        conf = ForecastConfidence.LOW.value
        basis = (
            f"всего {days_in_stock} дней в наличии — недостаточно данных, "
            f"мультипликатор ×{mult:.1f} применён но рекомендации не агрессивны"
        )
    elif total_units_sold < 5:
        conf = ForecastConfidence.LOW.value
        basis = f"всего {total_units_sold} продаж в окне — шум"
    elif days_in_stock / window >= 0.95:
        conf = ForecastConfidence.HIGH.value
        basis = f"в наличии {days_in_stock}/{window} дней — стабильная база"
    else:
        conf = ForecastConfidence.MEDIUM.value
        basis = (
            f"в наличии {days_in_stock}/{window} дней (×{mult:.2f}), "
            f"{days_out_of_stock} дней без остатка"
        )

    return VelocityResult(
        raw_avg_daily=raw,
        multiplier=mult,
        adjusted_daily=adjusted,
        confidence=conf,
        days_in_stock=days_in_stock,
        days_out_of_stock=days_out_of_stock,
        window_days=window,
        total_units_sold=total_units_sold,
        basis=basis,
    )
