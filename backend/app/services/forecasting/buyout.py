"""
Выкупаемость (buyout-rate) — пункт 1.

Формула (точно как у nepsell, проверено на 2-летней истории):

    buyout = (delivered − returned_after_delivery) / all_arrived

    где all_arrived = заказы, которые либо доехали до клиента, либо были
    отменены В ПУТИ (cancelled-in-transit считаются как «доехавшие до точки
    решения»).

Окно: последние 90 дней (ForecastDefaults.BUYOUT_WINDOW_DAYS).

Использование:
- Будущие продажи = заказы_в_пути_к_клиенту × buyout
- Возврат остатка = заказы_в_пути_ОТ_клиента × (1 − buyout)
  (вернутся на склад и снова доступны к продаже)
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.forecasting import ForecastConfidence, ForecastDefaults


@dataclass
class BuyoutResult:
    rate: float                # 0..1
    confidence: str            # ForecastConfidence
    sample_size: int           # сколько заказов в окне — для прозрачности UI
    delivered: int
    returned: int
    arrived_total: int
    basis: str                 # «почему такой rate / confidence»


def calc_buyout_rate(
    *,
    delivered: int,
    returned_after_delivery: int,
    arrived_total: int,
    window_days: int = ForecastDefaults.BUYOUT_WINDOW_DAYS,
) -> BuyoutResult:
    """Считает buyout-rate из агрегатов orders/returns за окно.

    Параметры:
    - delivered:               сколько заказов в статусе delivered за окно
    - returned_after_delivery: возвраты к нам после доставки клиенту
    - arrived_total:           delivered + cancelled-in-transit (всё дошедшее
                               до точки решения покупателя)

    Возвращает rate с confidence-меткой. При arrived_total < 30 → fallback
    BUYOUT_FALLBACK_RATE с confidence=low.
    """
    if arrived_total < 30:
        return BuyoutResult(
            rate=ForecastDefaults.BUYOUT_FALLBACK_RATE,
            confidence=ForecastConfidence.LOW.value,
            sample_size=arrived_total,
            delivered=delivered,
            returned=returned_after_delivery,
            arrived_total=arrived_total,
            basis=(
                f"sample_size={arrived_total} < 30 заказов в окне — "
                f"fallback {ForecastDefaults.BUYOUT_FALLBACK_RATE:.0%}"
            ),
        )

    actual_buyout = (delivered - returned_after_delivery) / max(arrived_total, 1)
    actual_buyout = max(0.0, min(1.0, actual_buyout))

    # Confidence по объёму выборки
    if arrived_total >= 200:
        conf = ForecastConfidence.HIGH.value
    elif arrived_total >= 60:
        conf = ForecastConfidence.MEDIUM.value
    else:
        conf = ForecastConfidence.LOW.value

    return BuyoutResult(
        rate=actual_buyout,
        confidence=conf,
        sample_size=arrived_total,
        delivered=delivered,
        returned=returned_after_delivery,
        arrived_total=arrived_total,
        basis=(
            f"{delivered} доставлено − {returned_after_delivery} возвратов / "
            f"{arrived_total} дошедших до решения покупателя"
        ),
    )


def project_future_sales(in_transit_to_customer: int, buyout: BuyoutResult) -> float:
    """Сколько из заказов «в пути к клиенту» дойдут до продажи."""
    return in_transit_to_customer * buyout.rate


def project_returning_stock(in_transit_from_customer: int, buyout: BuyoutResult) -> float:
    """Сколько из «в пути ОТ клиента» вернётся на склад как доступный остаток."""
    return in_transit_from_customer * (1 - buyout.rate)
