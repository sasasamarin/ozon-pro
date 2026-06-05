"""
Прогноз метрики для будущего периода на основе истории.

Алгоритм:
  1. Берём дневной ряд из истории за analysis_period
  2. Декомпозиция: тренд (линейная регрессия) + сезонность (по дню недели,
     взвешенно для длинных периодов — по дню года)
  3. Прогноз: тренд(d) × сезон(d)
  4. base_forecast = Σ прогноз по forecast_period
  5. Reliability: R² линейной модели + объём истории

Сезонные веса: pro-rata дня в общей сумме прогноза.
Если history < 30д — низкая надёжность, в badge показываем «оценочно».
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ForecastResult:
    metric_code: str
    history: list[tuple[date, float]]
    base_forecast: float
    forecast_series: list[tuple[date, float]]
    modified_series: list[tuple[date, float]] | None  # если задан target
    season_weights: dict[str, float]  # iso_date → вес, Σ=1.0
    reliability: str  # 'high' | 'medium' | 'low'
    reliability_pct: float  # 0-100 (комбо R² и history)
    note: str


# === SQL для разных метрик ===
# Возвращает ряд (day, value) для company/cabinet/sku scope

_METRIC_SQL = {
    "revenue": """
        SELECT t.operation_date::date AS day,
               SUM(t.accruals_for_sale)::float AS v
        FROM transactions t
        JOIN ozon_accounts oa ON oa.id = t.ozon_account_id
        WHERE oa.company_id = :cid
          AND t.operation_date >= :df AND t.operation_date <= :dt
          AND t.operation_type='OperationAgentDeliveredToCustomer'
          {extra}
        GROUP BY 1 ORDER BY 1
    """,
    "orders": """
        SELECT o.created_at::date AS day, COUNT(*)::float AS v
        FROM orders o
        JOIN ozon_accounts oa ON oa.id = o.ozon_account_id
        WHERE oa.company_id = :cid
          AND o.created_at >= :df AND o.created_at <= :dt
          AND o.status = 'delivered'
          {extra}
        GROUP BY 1 ORDER BY 1
    """,
    "units": """
        SELECT o.created_at::date AS day, SUM(oi.quantity)::float AS v
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN ozon_accounts oa ON oa.id = o.ozon_account_id
        WHERE oa.company_id = :cid
          AND o.created_at >= :df AND o.created_at <= :dt
          AND o.status = 'delivered'
          {extra}
        GROUP BY 1 ORDER BY 1
    """,
    "gross_profit": """
        SELECT t.operation_date::date AS day,
               (COALESCE(SUM(t.accruals_for_sale) FILTER (
                  WHERE t.operation_type='OperationAgentDeliveredToCustomer'), 0)
                - COALESCE(SUM(ABS(t.sale_commission) + ABS(t.delivery_to_customer)
                              + ABS(t.acquiring) + ABS(t.advertising)), 0))::float AS v
        FROM transactions t
        JOIN ozon_accounts oa ON oa.id = t.ozon_account_id
        WHERE oa.company_id = :cid
          AND t.operation_date >= :df AND t.operation_date <= :dt
          {extra}
        GROUP BY 1 ORDER BY 1
    """,
}


async def fetch_history(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    metric: str,
    analysis_start: date,
    analysis_end: date,
    cabinet_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
) -> list[tuple[date, float]]:
    """История метрики по дням для analysis-периода."""
    if metric not in _METRIC_SQL:
        raise ValueError(f"Unknown metric: {metric}")

    extra = ""
    params = {
        "cid": str(company_id),
        "df": analysis_start,
        "dt": analysis_end,
    }
    if cabinet_id:
        extra = "AND oa.id = :cab"
        params["cab"] = str(cabinet_id)
    if product_id:
        # orders/units → через order_items
        if metric in ("orders", "units"):
            extra += " AND EXISTS(SELECT 1 FROM order_items oi2 WHERE oi2.order_id=o.id AND oi2.product_id=:pid)"
        else:
            # revenue/gross_profit — попытка через product (если есть в транзакции — поле product_id)
            extra += " AND t.product_id = :pid"
        params["pid"] = str(product_id)

    sql = _METRIC_SQL[metric].format(extra=extra)
    rows = (await db.execute(text(sql), params)).all()
    return [(r.day, float(r.v or 0)) for r in rows]


def _linear_regression(history: list[tuple[date, float]]) -> tuple[float, float, float]:
    """Возвращает (slope, intercept, R²). x = индекс дня от начала."""
    if len(history) < 2:
        return 0.0, sum(v for _, v in history) / max(1, len(history)), 0.0
    n = len(history)
    xs = list(range(n))
    ys = [v for _, v in history]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = sum((x - mean_x) ** 2 for x in xs)
    if den_x == 0:
        return 0.0, mean_y, 0.0
    slope = num / den_x
    intercept = mean_y - slope * mean_x
    # R²
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    if ss_tot == 0:
        return slope, intercept, 1.0
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / ss_tot
    return slope, intercept, max(0.0, r2)


def _seasonal_weights_dow(history: list[tuple[date, float]]) -> dict[int, float]:
    """Вес дня недели = avg(value этого dow) / overall_avg."""
    sums = {i: 0.0 for i in range(7)}
    counts = {i: 0 for i in range(7)}
    for d, v in history:
        sums[d.weekday()] += v
        counts[d.weekday()] += 1
    avgs = {i: (sums[i] / counts[i] if counts[i] else 0) for i in range(7)}
    overall_avg = sum(v for _, v in history) / max(1, len(history))
    if overall_avg == 0:
        return {i: 1.0 for i in range(7)}
    return {i: (avgs[i] / overall_avg if avgs[i] > 0 else 1.0) for i in range(7)}


def compute_forecast(
    history: list[tuple[date, float]],
    forecast_start: date,
    forecast_end: date,
    target_value: float | None = None,
) -> ForecastResult:
    """Главный расчёт прогноза."""
    if not history:
        # Нет истории — равномерный 0-прогноз
        forecast_days = (forecast_end - forecast_start).days + 1
        forecast = [(forecast_start + timedelta(days=i), 0.0) for i in range(forecast_days)]
        return ForecastResult(
            metric_code="",
            history=[],
            base_forecast=0.0,
            forecast_series=forecast,
            modified_series=None,
            season_weights={d.isoformat(): 0.0 for d, _ in forecast},
            reliability="low",
            reliability_pct=0.0,
            note="Истории нет — нужны данные за период анализа.",
        )

    slope, intercept, r2 = _linear_regression(history)
    dow_weights = _seasonal_weights_dow(history)

    forecast_days = (forecast_end - forecast_start).days + 1
    history_end_idx = len(history)

    # Среднее по истории — для fallback и sanity check
    hist_avg = sum(v for _, v in history) / max(1, len(history))

    forecast: list[tuple[date, float]] = []
    for i in range(forecast_days):
        d = forecast_start + timedelta(days=i)
        x = history_end_idx + i
        trend_val = slope * x + intercept
        seasonal = dow_weights.get(d.weekday(), 1.0)
        val = max(0.0, trend_val * seasonal)
        forecast.append((d, val))

    base = sum(v for _, v in forecast)

    # Fallback: тренд ушёл в 0 (отрицательный slope при коротком ряду),
    # но история ненулевая → используем среднее × сезонные веса.
    used_fallback = False
    if base <= 0 and hist_avg > 0:
        used_fallback = True
        forecast = []
        for i in range(forecast_days):
            d = forecast_start + timedelta(days=i)
            seasonal = dow_weights.get(d.weekday(), 1.0)
            forecast.append((d, max(0.0, hist_avg * seasonal)))
        base = sum(v for _, v in forecast)

    # Модифицированный — масштаб под target
    modified: list[tuple[date, float]] | None = None
    if target_value is not None and base > 0:
        scale = target_value / base
        modified = [(d, v * scale) for d, v in forecast]

    # Season weights (для последующего распределения по дням)
    season_weights: dict[str, float] = {}
    if base > 0:
        for d, v in forecast:
            season_weights[d.isoformat()] = v / base
    else:
        equal = 1.0 / max(1, forecast_days)
        for d, _ in forecast:
            season_weights[d.isoformat()] = equal

    # Надёжность
    history_days = len(history)
    history_score = min(1.0, history_days / 90.0)  # 90+ дней = 100%
    reliability_pct = round((0.5 * r2 + 0.5 * history_score) * 100, 1)
    if reliability_pct >= 60:
        reliability = "high"
    elif reliability_pct >= 30:
        reliability = "medium"
    else:
        reliability = "low"

    note_parts = []
    if history_days < 30:
        note_parts.append(
            f"⚠ Истории всего {history_days}д с продажами — мало для точного прогноза. "
            f"Раздвинь период анализа на 60-90 дней или возьми другую метрику."
        )
    elif history_days < 90:
        note_parts.append(f"История {history_days}д (рекомендуется ≥90)")
    if r2 < 0.3:
        note_parts.append(f"R²={r2:.2f} — низкая статистическая значимость")
    if used_fallback:
        note_parts.append(
            "Тренд из истории ушёл в 0 → использовано среднее × сезонность"
        )
    note_parts.append("Прогноз = тренд × сезонность по дню недели.")
    note = " · ".join(note_parts)

    return ForecastResult(
        metric_code="",
        history=history,
        base_forecast=round(base, 2),
        forecast_series=forecast,
        modified_series=modified,
        season_weights=season_weights,
        reliability=reliability,
        reliability_pct=reliability_pct,
        note=note,
    )


# ============================================
# Распределение по SKU
# ============================================

async def distribute_by_sku_bottomup(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    metric: str,
    analysis_start: date,
    analysis_end: date,
    forecast_start: date,
    forecast_end: date,
    cabinet_ids: list[uuid.UUID] | None = None,
    product_ids: list[uuid.UUID] | None = None,
) -> list[dict]:
    """
    Bottom-up: для каждого выбранного SKU считаем СВОЙ прогноз на forecast_period
    как стартовое значение plan_value. Юзер потом может править вручную.

    Возвращает: [{product_id, sku, name, offer_id, cabinet_id, cabinet_name,
                  analysis_value, forecast_value (= стартовое plan_value), share_pct}]
    """
    # 1. Берём список SKU из истории с метриками за analysis-период
    extra_oa = ""
    extra_p = ""
    params: dict = {
        "cid": str(company_id), "df": analysis_start, "dt": analysis_end,
    }
    if cabinet_ids:
        extra_oa = "AND oa.id = ANY(:cabs)"
        params["cabs"] = [str(c) for c in cabinet_ids]
    if product_ids:
        extra_p = "AND p.id = ANY(:pids)"
        params["pids"] = [str(p) for p in product_ids]

    if metric == "revenue":
        sql = f"""
            SELECT p.id::text AS product_id, p.offer_id, p.name,
                   oa.id::text AS cabinet_id, oa.name AS cabinet_name,
                   COALESCE(SUM(t.accruals_for_sale), 0)::float AS analysis_value
            FROM transactions t
            JOIN ozon_accounts oa ON oa.id = t.ozon_account_id
            JOIN products p ON p.id = t.product_id
            WHERE oa.company_id = :cid
              AND t.operation_date >= :df AND t.operation_date <= :dt
              AND t.operation_type='OperationAgentDeliveredToCustomer'
              {extra_oa} {extra_p}
            GROUP BY p.id, p.offer_id, p.name, oa.id, oa.name
            HAVING SUM(t.accruals_for_sale) > 0
            ORDER BY analysis_value DESC
            LIMIT 500
        """
    elif metric in ("orders", "units"):
        agg = "COUNT(DISTINCT o.id)::float" if metric == "orders" else "SUM(oi.quantity)::float"
        sql = f"""
            SELECT p.id::text AS product_id, p.offer_id, p.name,
                   oa.id::text AS cabinet_id, oa.name AS cabinet_name,
                   {agg} AS analysis_value
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            JOIN ozon_accounts oa ON oa.id = o.ozon_account_id
            JOIN products p ON p.id = oi.product_id
            WHERE oa.company_id = :cid
              AND o.created_at >= :df AND o.created_at <= :dt
              AND o.status = 'delivered'
              {extra_oa} {extra_p}
            GROUP BY p.id, p.offer_id, p.name, oa.id, oa.name
            HAVING {agg} > 0
            ORDER BY analysis_value DESC
            LIMIT 500
        """
    else:
        sql = f"""
            SELECT p.id::text AS product_id, p.offer_id, p.name,
                   oa.id::text AS cabinet_id, oa.name AS cabinet_name,
                   COALESCE(SUM(t.accruals_for_sale), 0)::float AS analysis_value
            FROM transactions t
            JOIN ozon_accounts oa ON oa.id = t.ozon_account_id
            JOIN products p ON p.id = t.product_id
            WHERE oa.company_id = :cid
              AND t.operation_date >= :df AND t.operation_date <= :dt
              {extra_oa} {extra_p}
            GROUP BY p.id, p.offer_id, p.name, oa.id, oa.name
            HAVING SUM(t.accruals_for_sale) > 0
            ORDER BY analysis_value DESC
            LIMIT 500
        """

    rows = (await db.execute(text(sql), params)).all()

    # 2. Для каждого SKU считаем прогноз на forecast_period
    #    Простая модель: line projection — analysis_value × (forecast_days / analysis_days)
    analysis_days = (analysis_end - analysis_start).days + 1
    forecast_days = (forecast_end - forecast_start).days + 1
    if analysis_days <= 0:
        raise ValueError(f"analysis_end ({analysis_end}) меньше analysis_start ({analysis_start})")
    if forecast_days <= 0:
        raise ValueError(f"forecast_end ({forecast_end}) меньше forecast_start ({forecast_start})")
    scale = forecast_days / analysis_days
    # На случай если периоды равны (scale=1) — план = факт. Если прогноз короче
    # анализа — план меньше факта пропорционально. Это правильно.

    items: list[dict] = []
    total_forecast = 0.0
    for r in rows:
        analysis_v = float(r.analysis_value or 0)
        forecast_v = analysis_v * scale
        total_forecast += forecast_v
        items.append({
            "product_id": r.product_id, "sku": r.offer_id,
            "name": r.name, "offer_id": r.offer_id,
            "cabinet_id": r.cabinet_id, "cabinet_name": r.cabinet_name,
            "analysis_value": round(analysis_v, 2),
            "forecast_value": round(forecast_v, 2),
            "plan_value": round(forecast_v, 2),  # стартовое = прогноз
            "share_pct": 0.0,  # пересчитаем ниже
        })

    # 3. Доли — от total_forecast
    for it in items:
        it["share_pct"] = round(
            (it["forecast_value"] / total_forecast * 100) if total_forecast > 0 else 0,
            4,
        )

    return items


async def distribute_by_sku(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    metric: str,
    analysis_start: date,
    analysis_end: date,
    cabinet_id: uuid.UUID | None = None,
    target_value: float,
) -> list[dict]:
    """
    Возвращает список SKU с распределением:
      [{product_id, sku, name, offer_id, analysis_value, share_pct, plan_value}]

    share_pct = analysis_value(sku) / Σ analysis_value
    plan_value = target_value × share_pct
    """
    extra = ""
    params = {"cid": str(company_id), "df": analysis_start, "dt": analysis_end}
    if cabinet_id:
        extra = "AND oa.id = :cab"
        params["cab"] = str(cabinet_id)

    # SQL зависит от метрики
    if metric == "revenue":
        sql = f"""
            SELECT p.id::text AS product_id, p.offer_id, p.name,
                   COALESCE(SUM(t.accruals_for_sale), 0)::float AS analysis_value
            FROM transactions t
            JOIN ozon_accounts oa ON oa.id = t.ozon_account_id
            JOIN products p ON p.id = t.product_id
            WHERE oa.company_id = :cid
              AND t.operation_date >= :df AND t.operation_date <= :dt
              AND t.operation_type='OperationAgentDeliveredToCustomer'
              {extra}
            GROUP BY p.id, p.offer_id, p.name
            HAVING SUM(t.accruals_for_sale) > 0
            ORDER BY analysis_value DESC
            LIMIT 200
        """
    elif metric in ("orders", "units"):
        agg = "COUNT(DISTINCT o.id)::float" if metric == "orders" else "SUM(oi.quantity)::float"
        sql = f"""
            SELECT p.id::text AS product_id, p.offer_id, p.name,
                   {agg} AS analysis_value
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            JOIN ozon_accounts oa ON oa.id = o.ozon_account_id
            JOIN products p ON p.id = oi.product_id
            WHERE oa.company_id = :cid
              AND o.created_at >= :df AND o.created_at <= :dt
              AND o.status = 'delivered'
              {extra}
            GROUP BY p.id, p.offer_id, p.name
            HAVING {agg} > 0
            ORDER BY analysis_value DESC
            LIMIT 200
        """
    else:
        # fallback — proxy через revenue
        sql = f"""
            SELECT p.id::text AS product_id, p.offer_id, p.name,
                   COALESCE(SUM(t.accruals_for_sale), 0)::float AS analysis_value
            FROM transactions t
            JOIN ozon_accounts oa ON oa.id = t.ozon_account_id
            JOIN products p ON p.id = t.product_id
            WHERE oa.company_id = :cid
              AND t.operation_date >= :df AND t.operation_date <= :dt
              {extra}
            GROUP BY p.id, p.offer_id, p.name
            HAVING SUM(t.accruals_for_sale) > 0
            ORDER BY analysis_value DESC
            LIMIT 200
        """

    rows = (await db.execute(text(sql), params)).all()
    total = sum(float(r.analysis_value or 0) for r in rows) or 1.0

    items: list[dict] = []
    for r in rows:
        v = float(r.analysis_value or 0)
        share = v / total
        items.append({
            "product_id": r.product_id,
            "sku": r.offer_id,
            "name": r.name,
            "offer_id": r.offer_id,
            "analysis_value": round(v, 2),
            "share_pct": round(share * 100, 4),
            "plan_value": round(target_value * share, 2),
        })
    return items
