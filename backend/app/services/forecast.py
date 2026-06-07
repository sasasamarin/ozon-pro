"""
Сервис прогноза метрик для раздела «План продаж».

Алгоритм:
  1. Берёт исторический ряд из transactions за analysis-период
  2. Разбивает на тренд (линейная регрессия по дням) + сезонность (по дням недели)
  3. Возвращает ForecastResult с датами, историей, прогнозом и метаданными

Numpy не используется — чистый Python (нет в зависимостях проекта).
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

METRIC_QUERY = {
    "revenue": "COALESCE(SUM(accruals_for_sale), 0)",
    "orders": "COUNT(DISTINCT posting_number) FILTER (WHERE posting_number IS NOT NULL)",
    "units": "COUNT(*)",
    "margin": (
        "COALESCE(SUM(accruals_for_sale), 0) + "
        "COALESCE(SUM(sale_commission), 0) + "
        "COALESCE(SUM(delivery_to_customer), 0) + "
        "COALESCE(SUM(return_logistics), 0)"
    ),
}


@dataclass
class ForecastResult:
    cabinet_id: uuid.UUID
    metric_code: str
    dates: list[str]
    history: list[Optional[float]]
    base_forecast: list[float]
    total_forecast: float
    r2: float
    data_points_count: int
    badge: str


def _linear_regression(xs: list[int], ys: list[float]) -> tuple[float, float, float]:
    """Возвращает (slope, intercept, r2). Чистый Python, без numpy."""
    n = len(xs)
    if n < 2:
        return 0.0, (ys[0] if ys else 0.0), 0.0
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    ss_xy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    ss_xx = sum((x - x_mean) ** 2 for x in xs)
    if ss_xx == 0:
        return 0.0, y_mean, 0.0
    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean
    y_pred = [slope * x + intercept for x in xs]
    ss_res = sum((y - yp) ** 2 for y, yp in zip(ys, y_pred))
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    r2 = max(0.0, 1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    return slope, intercept, r2


def _dow_factors(dates: list[date], values: list[float]) -> dict[int, float]:
    """
    Сезонность по дням недели.
    Возвращает коэффициент dow → средний_день / общее_среднее.
    0=пн, 6=вс.
    """
    overall = sum(values) / len(values) if values else 0.0
    if overall == 0:
        return {}
    by_dow: dict[int, list[float]] = defaultdict(list)
    for d, v in zip(dates, values):
        by_dow[d.weekday()].append(v)
    return {
        dow: (sum(vals) / len(vals)) / overall
        for dow, vals in by_dow.items()
    }


async def forecast(
    *,
    metric: str,
    analysis_start: date,
    analysis_end: date,
    forecast_start: date,
    forecast_end: date,
    cabinet_id: uuid.UUID,
    db: AsyncSession,
    skus: Optional[list[str]] = None,
) -> ForecastResult:
    """
    Прогноз метрики по историческим транзакциям.

    skus — если передан непустой список, фильтрует только по этим артикулам.
    Статус транзакций не фильтруется — берём все accruals_for_sale > 0.
    """
    agg_expr = METRIC_QUERY.get(metric, METRIC_QUERY["revenue"])

    sku_filter = ""
    params: dict = {
        "cabinet_id": str(cabinet_id),
        "ts_from": analysis_start,
        "ts_to": analysis_end,
    }
    if skus:
        sku_filter = "AND posting_number IN (SELECT posting_number FROM order_items WHERE offer_id = ANY(:skus))"
        params["skus"] = skus

    sql = text(f"""
        SELECT
            DATE(time AT TIME ZONE 'Europe/Moscow') AS day,
            {agg_expr} AS value
        FROM transactions
        WHERE ozon_account_id = :cabinet_id::uuid
          AND time >= :ts_from
          AND time <  :ts_to + INTERVAL '1 day'
          {sku_filter}
        GROUP BY 1
        ORDER BY 1
    """)

    rows = (await db.execute(sql, params)).mappings().all()

    # Индексируем по дате
    hist_by_date: dict[date, float] = {r["day"]: float(r["value"] or 0) for r in rows}

    # Строим сплошной ряд по дням analysis-периода (вставляем 0 за отсутствующие дни)
    n_analysis = (analysis_end - analysis_start).days + 1
    history_dates = [analysis_start + timedelta(days=i) for i in range(n_analysis)]
    history_values = [hist_by_date.get(d, 0.0) for d in history_dates]

    data_points = sum(1 for v in history_values if v > 0)

    # Линейная регрессия по индексу дня
    xs = list(range(n_analysis))
    slope, intercept, r2 = _linear_regression(xs, history_values)

    # Сезонность по дням недели (только по ненулевым дням)
    nz_dates = [d for d, v in zip(history_dates, history_values) if v > 0]
    nz_values = [v for v in history_values if v > 0]
    dow_fac = _dow_factors(nz_dates, nz_values) if nz_values else {}

    # Прогноз на forecast-период
    n_forecast = (forecast_end - forecast_start).days + 1
    forecast_dates = [forecast_start + timedelta(days=i) for i in range(n_forecast)]

    # Базовый индекс для тренда: forecast_start — день n_analysis + offset
    base_x = n_analysis
    forecast_values: list[float] = []
    for i, fd in enumerate(forecast_dates):
        trend_val = slope * (base_x + i) + intercept
        trend_val = max(0.0, trend_val)
        fac = dow_fac.get(fd.weekday(), 1.0)
        # Комбинируем: 70% тренд + 30% сезонность
        val = trend_val * (0.7 + 0.3 * fac)
        forecast_values.append(round(max(0.0, val), 2))

    total = round(sum(forecast_values), 2)

    if data_points < 30:
        badge = "low"
    elif data_points < 90:
        badge = "medium"
    else:
        badge = "high"

    return ForecastResult(
        cabinet_id=cabinet_id,
        metric_code=metric,
        dates=[d.isoformat() for d in history_dates + forecast_dates],
        history=[round(v, 2) for v in history_values] + [None] * n_forecast,
        base_forecast=[None] * n_analysis + forecast_values,  # type: ignore[list-item]
        total_forecast=total,
        r2=round(r2, 4),
        data_points_count=data_points,
        badge=badge,
    )
