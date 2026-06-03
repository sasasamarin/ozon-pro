"""
Source A — сезонность из СВОЕЙ истории SKU.
Все расчёты на order_items × orders (и transactions для выручки).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date as date_cls, timedelta
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


Metric = Literal["orders", "buyouts", "revenue"]
Granularity = Literal["month", "week"]


@dataclass
class HistoryStats:
    days_history: int            # длина истории в днях (max_date - min_date)
    confidence: str              # 'high' | 'medium' | 'low' | 'insufficient'
    confidence_note: str         # человекочитаемое объяснение
    yoy_full_years: int          # сколько полных лет YoY можно построить


def _confidence_from_days(days: int) -> tuple[str, str, int]:
    """Gating: правила из брифа.

    ≥730  → high       (полноценный анализ)
    365–729 → medium   (YoY частичный, бейдж «1 год — низкая уверенность»)
    90–364 → low       (только месячный профиль, «предварительно»)
    <90  → insufficient
    """
    if days >= 730:
        return "high", "Достаточно истории для полноценного сезонного анализа", 2
    if days >= 365:
        return "medium", "Есть 1 год истории — YoY частичный, низкая уверенность", 1
    if days >= 90:
        return "low", f"Только {days} дней истории — показываем профиль предварительно, без YoY", 0
    return "insufficient", f"Всего {days} дней — недостаточно для сезонного анализа", 0


async def history_for_product(
    db: AsyncSession, product_id: uuid.UUID
) -> HistoryStats:
    r = (await db.execute(text("""
        SELECT MIN(DATE(o.order_created_at)) AS first_d,
               MAX(DATE(o.order_created_at)) AS last_d
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE oi.product_id = :pid
    """), {"pid": str(product_id)})).first()
    if not r or not r.first_d:
        c, note, _ = _confidence_from_days(0)
        return HistoryStats(0, c, note, 0)
    days = (r.last_d - r.first_d).days
    c, note, yy = _confidence_from_days(days)
    return HistoryStats(days, c, note, yy)


async def history_for_cabinet(
    db: AsyncSession, cabinet_id: uuid.UUID
) -> HistoryStats:
    r = (await db.execute(text("""
        SELECT MIN(DATE(o.order_created_at)) AS first_d,
               MAX(DATE(o.order_created_at)) AS last_d
        FROM orders o WHERE o.ozon_account_id = :cid
    """), {"cid": str(cabinet_id)})).first()
    if not r or not r.first_d:
        c, note, _ = _confidence_from_days(0)
        return HistoryStats(0, c, note, 0)
    days = (r.last_d - r.first_d).days
    c, note, yy = _confidence_from_days(days)
    return HistoryStats(days, c, note, yy)


def _metric_select(metric: Metric) -> str:
    """SQL фрагмент SUM(...) для выбранной метрики."""
    if metric == "orders":
        return "SUM(oi.quantity)::float"
    if metric == "buyouts":
        return "SUM(oi.quantity) FILTER (WHERE o.status='delivered')::float"
    if metric == "revenue":
        return "SUM(oi.price * oi.quantity)::float"
    raise ValueError(metric)


# ===== ПРОФИЛЬ (индексы по месяцу/неделе) ==================================


async def profile(
    db: AsyncSession, *,
    product_id: uuid.UUID | None = None,
    cabinet_id: uuid.UUID | None = None,
    metric: Metric = "orders",
    granularity: Granularity = "month",
) -> dict:
    """
    Сезонный индекс = (сумма за период) / (среднегодовая сумма по той же сетке).
    >1 = пик, <1 = провал.

    Агрегация: суммы складываем, индексы пересчитываем (а не среднее от средних).
    Если у юзера 1.5 года истории — берём ВСЁ что есть, считаем индексы.
    Считаем по тому же признаку (1-12 месяц / 1-53 неделя).
    """
    if not product_id and not cabinet_id:
        raise ValueError("product_id or cabinet_id required")

    metric_sum = _metric_select(metric)
    where = "1=1"
    params: dict = {}
    if product_id:
        where += " AND oi.product_id = :pid"
        params["pid"] = str(product_id)
    if cabinet_id:
        where += " AND o.ozon_account_id = :cid"
        params["cid"] = str(cabinet_id)

    if granularity == "month":
        # bucket = месяц года (1..12)
        bucket_sql = "EXTRACT(MONTH FROM o.order_created_at)::int"
    else:
        bucket_sql = "EXTRACT(WEEK FROM o.order_created_at)::int"

    rows = (await db.execute(text(f"""
        SELECT {bucket_sql} AS bucket,
               {metric_sum}    AS val,
               COUNT(DISTINCT EXTRACT(YEAR FROM o.order_created_at)) AS years_seen
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE {where}
        GROUP BY 1 ORDER BY 1
    """), params)).all()

    # Среднегодовая база = средний bucket-value. Если бакетов нет — индекс None.
    vals = [float(r.val or 0) for r in rows]
    avg = sum(vals) / len(vals) if vals else 0
    buckets = []
    for r in rows:
        v = float(r.val or 0)
        idx = (v / avg) if avg else None
        buckets.append({
            "bucket": int(r.bucket),
            "value": v,
            "index": round(idx, 3) if idx is not None else None,
            "years_seen": int(r.years_seen or 0),
        })

    # Заполним пропущенные бакеты None'ами для UI (например, нет данных за июль)
    full = list(range(1, 13)) if granularity == "month" else list(range(1, 54))
    by = {b["bucket"]: b for b in buckets}
    result = []
    for x in full:
        result.append(by.get(x, {
            "bucket": x, "value": 0.0, "index": None, "years_seen": 0,
        }))
    return {"buckets": result, "annual_avg": round(avg, 2)}


# ===== YoY (наложение лет) =================================================


async def yoy(
    db: AsyncSession, *,
    product_id: uuid.UUID | None = None,
    cabinet_id: uuid.UUID | None = None,
    metric: Metric = "orders",
) -> dict:
    """
    Ось X = day-of-year (1..366), линии = годы. Recharts строит как multi-series.
    Группируем по дню года (с учётом високосного — 29 фев в год без него = None).
    """
    metric_sum = _metric_select(metric)
    where = "1=1"
    params: dict = {}
    if product_id:
        where += " AND oi.product_id = :pid"
        params["pid"] = str(product_id)
    if cabinet_id:
        where += " AND o.ozon_account_id = :cid"
        params["cid"] = str(cabinet_id)

    rows = (await db.execute(text(f"""
        SELECT EXTRACT(YEAR FROM o.order_created_at)::int       AS y,
               EXTRACT(DOY  FROM o.order_created_at)::int       AS doy,
               {metric_sum}                                     AS val
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE {where}
        GROUP BY 1, 2 ORDER BY 1, 2
    """), params)).all()

    # На фронт: list[{doy: 1..366, "2025": value, "2026": value}]
    years = sorted({int(r.y) for r in rows})
    by_doy: dict[int, dict] = {}
    for r in rows:
        d = by_doy.setdefault(int(r.doy), {"doy": int(r.doy)})
        d[str(int(r.y))] = float(r.val or 0)
    series = [by_doy[d] for d in sorted(by_doy.keys())]
    return {"years": years, "series": series}


# ===== Автодетект сезонности ===============================================


async def detect_cabinet(
    db: AsyncSession, *,
    cabinet_id: uuid.UUID,
    metric: Metric = "buyouts",
    threshold_ratio: float = 1.5,
) -> dict:
    """
    Товар «сезонный» если max(месячный индекс) / min(месячный индекс) > threshold
    И истории ≥365 дней. Иначе — «ровный» или «недостаточно данных».

    Помесячный индекс = (продажи в месяце) / (среднемесячные).

    ОПТИМИЗАЦИЯ: всё одним SQL вместо N+N*M запросов.
    19 SKU × profile с историей раньше брали 60+ сек (timeout).
    Теперь — одна агрегация GROUP BY product_id, month.
    """
    metric_sum = _metric_select(metric)

    # Один SQL: для каждого SKU собираем (min_date, max_date, помесячные суммы)
    rows = (await db.execute(text(f"""
        WITH per_sku_month AS (
            SELECT
                oi.product_id,
                EXTRACT(MONTH FROM o.order_created_at)::int AS m,
                {metric_sum} AS val
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            JOIN products p ON p.id = oi.product_id
            WHERE p.ozon_account_id = :cid AND p.archived_at IS NULL
            GROUP BY 1, 2
        ),
        per_sku_history AS (
            SELECT
                oi.product_id,
                MIN(DATE(o.order_created_at)) AS first_d,
                MAX(DATE(o.order_created_at)) AS last_d
            FROM order_items oi JOIN orders o ON o.id = oi.order_id
            JOIN products p ON p.id = oi.product_id
            WHERE p.ozon_account_id = :cid AND p.archived_at IS NULL
            GROUP BY 1
        )
        SELECT p.id::text AS id, p.name, p.offer_id, p.ozon_sku,
               h.first_d, h.last_d,
               COALESCE(json_agg(
                   json_build_object('m', psm.m, 'val', psm.val)
                   ORDER BY psm.m
               ) FILTER (WHERE psm.m IS NOT NULL), '[]'::json) AS month_data
        FROM products p
        LEFT JOIN per_sku_history h ON h.product_id = p.id
        LEFT JOIN per_sku_month psm ON psm.product_id = p.id
        WHERE p.ozon_account_id = :cid AND p.archived_at IS NULL
        GROUP BY p.id, p.name, p.offer_id, p.ozon_sku, h.first_d, h.last_d
        ORDER BY p.name
    """), {"cid": str(cabinet_id)})).all()

    if not rows:
        return {"items": []}

    items = []
    for r in rows:
        days = (r.last_d - r.first_d).days if (r.first_d and r.last_d) else 0
        c, note, _ = _confidence_from_days(days)
        verdict = "insufficient"
        peak_month: int | None = None
        amplitude: float | None = None

        if days >= 365:
            md = r.month_data if isinstance(r.month_data, list) else (r.month_data or [])
            vals = [(int(x["m"]), float(x["val"] or 0)) for x in md if x.get("m")]
            if len(vals) >= 6:
                avg = sum(v for _, v in vals) / len(vals)
                if avg > 0:
                    indexes = [(m, v / avg) for m, v in vals]
                    only_idx = [i for _, i in indexes]
                    lo, hi = min(only_idx), max(only_idx)
                    amplitude = round(hi / lo, 2) if lo else None
                    if amplitude and amplitude > threshold_ratio:
                        verdict = "seasonal"
                        peak_month = max(indexes, key=lambda x: x[1])[0]
                    else:
                        verdict = "flat"

        items.append({
            "product_id": r.id, "name": r.name,
            "offer_id": r.offer_id, "ozon_sku": r.ozon_sku,
            "days_history": days,
            "confidence": c,
            "verdict": verdict,
            "peak_month": peak_month,
            "amplitude_ratio": amplitude,
        })
    return {"items": items}


# ===== Прогноз пика =========================================================


async def forecast_peak(
    db: AsyncSession, *,
    product_id: uuid.UUID,
    metric: Metric = "buyouts",
    horizon_months: int = 12,
) -> dict:
    """
    Простой прогноз: для каждого месяца следующих 12 берём исторический
    индекс × среднюю продажу за последние 90 дней.

    source='model' — это оценка, не факт. UI помечает соответственно.
    """
    hs = await history_for_product(db, product_id)
    if hs.days_history < 90:
        return {
            "source": "model",
            "confidence": hs.confidence,
            "note": hs.confidence_note,
            "rows": [],
        }
    prof = await profile(
        db, product_id=product_id, metric=metric, granularity="month",
    )
    # Текущий рейт продаж — последние 90 дней
    r = (await db.execute(text(f"""
        SELECT {_metric_select(metric)} AS val,
               (MAX(DATE(o.order_created_at)) - MIN(DATE(o.order_created_at)))::int + 1 AS days
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE oi.product_id = :pid
          AND o.order_created_at >= NOW() - INTERVAL '90 days'
    """), {"pid": str(product_id)})).first()
    val = float(r.val or 0) if r else 0
    days = int(r.days or 1) if r else 1
    avg_daily = val / days if days else 0
    base_monthly = avg_daily * 30

    # Горизонт: следующие N месяцев
    from datetime import date
    today = date.today()
    rows = []
    for i in range(horizon_months):
        month = ((today.month - 1 + i) % 12) + 1
        year = today.year + ((today.month - 1 + i) // 12)
        idx_row = next((b for b in prof["buckets"] if b["bucket"] == month), None)
        idx = (idx_row or {}).get("index")
        forecast = (base_monthly * idx) if idx else None
        rows.append({
            "year": year, "month": month,
            "seasonal_index": idx,
            "forecast_units": round(forecast, 1) if forecast is not None else None,
        })
    return {
        "source": "model",
        "confidence": hs.confidence,
        "note": hs.confidence_note,
        "base_monthly": round(base_monthly, 1),
        "rows": rows,
    }
