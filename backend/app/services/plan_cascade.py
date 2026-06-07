"""
Сервис каскадного пересчёта «что изменится при изменении метрики».

Каскад: +delta кликов (CTR) → +заказы (conversion) → +продажи (buyout)
        → +выручка (avg_check) → −комиссия (41%) → маржа

Коэффициенты читаются из analytics_daily за analysis-период плана.
Если R² коэффициента < 0.3 → source-флаг = 'estimated'.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

OZON_COMMISSION_PCT = 0.41  # подтверждено на данных (CLAUDE.md)
R2_ESTIMATED_THRESHOLD = 0.3


def _r2_flag(r2: float) -> str:
    return "estimated" if r2 < R2_ESTIMATED_THRESHOLD else "api"


def _safe_div(num: float, den: float, default: float = 0.0) -> float:
    return num / den if den else default


def _simple_r2(values: list[float]) -> float:
    """
    R² однозначных коэффициентов — оцениваем стабильность через CV.

    R² = 1 − (std / mean)² — грубая прокси. Если mean=0 → 0.
    """
    if len(values) < 3:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = variance ** 0.5
    cv = std / mean
    return max(0.0, 1.0 - cv ** 2)


async def _get_plan_scope(plan_id: int, db: AsyncSession) -> Optional[dict]:
    """Читает запись sales_plan по plan_id."""
    row = (await db.execute(
        text("SELECT * FROM sales_plan WHERE id = :id"),
        {"id": plan_id},
    )).mappings().one_or_none()
    return dict(row) if row else None


async def _analytics_coefficients(
    *,
    cabinet_id: str,
    analysis_start: date,
    analysis_end: date,
    sku: Optional[str],
    db: AsyncSession,
) -> dict:
    """
    Читает analytics_daily для кабинета/SKU за analysis-период.
    Возвращает агрегированные коэффициенты и raw-ряды для R².
    """
    sku_join = ""
    sku_filter = ""
    params: dict = {
        "cabinet_id": cabinet_id,
        "date_from": analysis_start,
        "date_to": analysis_end,
    }

    if sku:
        sku_join = "JOIN products p ON p.id = ad.product_id"
        sku_filter = "AND p.offer_id = :sku"
        params["sku"] = sku

    sql = text(f"""
        SELECT
            ad.date,
            COALESCE(ad.hits_view_search, 0)   AS impressions,
            COALESCE(ad.hits_tocart_search, 0) AS tocart,
            COALESCE(ad.session_view, 0)        AS sessions,
            COALESCE(ad.ordered_units, 0)       AS orders,
            COALESCE(ad.delivered_units, 0)     AS delivered,
            COALESCE(ad.returns, 0)             AS returns,
            COALESCE(ad.revenue, 0)             AS revenue
        FROM analytics_daily ad
        {sku_join}
        JOIN products pr ON pr.id = ad.product_id
        JOIN ozon_accounts oa ON oa.id = pr.ozon_account_id
        WHERE oa.id = :cabinet_id::uuid
          AND ad.date >= :date_from
          AND ad.date <= :date_to
          {sku_filter}
        ORDER BY ad.date
    """)

    rows = (await db.execute(sql, params)).mappings().all()

    if not rows:
        return {
            "ctr": 0.0, "ctr_r2": 0.0,
            "conv": 0.0, "conv_r2": 0.0,
            "buyout": 0.0, "buyout_r2": 0.0,
            "avg_check": 0.0, "avg_check_r2": 0.0,
            "cpc": None, "cpc_r2": 0.0,
            "data_days": 0,
        }

    daily_ctr, daily_conv, daily_buyout, daily_check = [], [], [], []

    total_impressions = total_tocart = total_sessions = 0.0
    total_orders = total_delivered = total_returns = total_revenue = 0.0

    for r in rows:
        imp = float(r["impressions"])
        tc = float(r["tocart"])
        sess = float(r["sessions"])
        ord_ = float(r["orders"])
        del_ = float(r["delivered"])
        ret_ = float(r["returns"])
        rev = float(r["revenue"])

        total_impressions += imp
        total_tocart += tc
        total_sessions += sess
        total_orders += ord_
        total_delivered += del_
        total_returns += ret_
        total_revenue += rev

        if imp > 0:
            daily_ctr.append(tc / imp)
        if sess > 0:
            daily_conv.append(ord_ / sess)
        if ord_ > 0:
            daily_buyout.append((del_ - ret_) / ord_)
            daily_check.append(rev / ord_)

    ctr = _safe_div(total_tocart, total_impressions)
    conv = _safe_div(total_orders, total_sessions)
    buyout = _safe_div(total_delivered - total_returns, total_orders)
    avg_check = _safe_div(total_revenue, total_orders)

    return {
        "ctr": ctr,
        "ctr_r2": _simple_r2(daily_ctr),
        "conv": conv,
        "conv_r2": _simple_r2(daily_conv),
        "buyout": buyout,
        "buyout_r2": _simple_r2(daily_buyout),
        "avg_check": avg_check,
        "avg_check_r2": _simple_r2(daily_check),
        "cpc": None,   # CPC из Performance API — недоступен в этом контексте
        "cpc_r2": 0.0,
        "data_days": len(rows),
    }


async def simulate_plan_change(
    plan_id: int,
    metric: str,
    delta: float,
    db: AsyncSession,
) -> dict:
    """
    Каскадный пересчёт при изменении метрики на delta.

    metric: 'clicks' | 'orders' | 'revenue' | 'budget'
    delta: абсолютное изменение (не %)

    Возвращает dict с cascade и sources.
    """
    plan = await _get_plan_scope(plan_id, db)
    if not plan:
        return {
            "error": "plan_not_found",
            "cascade": {},
            "sources": {},
        }

    analysis_start: Optional[date] = plan.get("analysis_start")
    analysis_end: Optional[date] = plan.get("analysis_end")
    scope_ref: Optional[str] = plan.get("scope_ref")

    # Если нет analysis-периода — фолбэк на period
    if not analysis_start:
        analysis_start = plan["period_start"]
    if not analysis_end:
        analysis_end = plan["period_end"]

    # Кабинет определяем через scope_ref (для scope_type=cabinet — это cabinet_id)
    cabinet_id = scope_ref if plan.get("scope_type") == "cabinet" else None
    sku = scope_ref if plan.get("scope_type") == "sku" else None

    if not cabinet_id:
        # Если нет конкретного кабинета — нет данных для коэффициентов
        return {
            "plan_id": plan_id,
            "metric": metric,
            "delta": delta,
            "cascade": {"note": "Кабинет не определён в scope — каскад недоступен"},
            "sources": {"all": "estimated"},
        }

    coef = await _analytics_coefficients(
        cabinet_id=cabinet_id,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        sku=sku,
        db=db,
    )

    sources: dict[str, str] = {}

    # ── Каскад ────────────────────────────────────────────────────────────────
    # Входная точка: clicks (или другая метрика)
    delta_clicks = 0.0
    delta_orders = 0.0
    delta_revenue = 0.0

    if metric == "clicks":
        delta_clicks = delta
    elif metric == "orders":
        delta_orders = delta
    elif metric == "revenue":
        delta_revenue = delta
    elif metric == "budget":
        cpc = coef["cpc"] or 0.0
        delta_clicks = delta / cpc if cpc > 0 else 0.0
        sources["cpc"] = "estimated"  # CPC недоступен без Performance API

    # clicks → orders
    if delta_clicks and not delta_orders:
        conv = coef["conv"]
        ctr = coef["ctr"]
        delta_sessions = delta_clicks / ctr if ctr > 0 else delta_clicks
        delta_orders = delta_sessions * conv
        sources["ctr"] = _r2_flag(coef["ctr_r2"])
        sources["conv"] = _r2_flag(coef["conv_r2"])

    # orders → sales (после выкупа)
    buyout = coef["buyout"] if coef["buyout"] > 0 else 0.6  # дефолт 60%
    delta_sales = delta_orders * buyout if delta_orders else 0.0
    sources["buyout"] = _r2_flag(coef["buyout_r2"])

    # sales → revenue
    avg_check = coef["avg_check"]
    if not delta_revenue:
        delta_revenue = delta_sales * avg_check
    sources["avg_check"] = _r2_flag(coef["avg_check_r2"])

    # revenue → commission → margin
    delta_commission = delta_revenue * OZON_COMMISSION_PCT
    delta_margin = delta_revenue - delta_commission
    sources["commission"] = "api"  # 41% — подтверждено

    cascade = {
        "delta_clicks":     round(delta_clicks, 0),
        "delta_sessions":   round(delta_clicks / coef["ctr"] if coef["ctr"] > 0 else delta_clicks, 0),
        "delta_orders":     round(delta_orders, 1),
        "delta_sales":      round(delta_sales, 1),
        "delta_revenue":    round(delta_revenue, 2),
        "delta_commission": round(delta_commission, 2),
        "delta_margin":     round(delta_margin, 2),
        "coefficients": {
            "ctr":       round(coef["ctr"], 4),
            "conv":      round(coef["conv"], 4),
            "buyout":    round(buyout, 4),
            "avg_check": round(avg_check, 2),
        },
        "data_days": coef["data_days"],
    }

    return {
        "plan_id": plan_id,
        "metric": metric,
        "delta": delta,
        "cascade": cascade,
        "sources": sources,
    }
