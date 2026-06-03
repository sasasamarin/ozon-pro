"""
AI Phase 1 (FLOWOI_AI_TZ §6): реестр инструментов.

data-tools — переиспользуют существующие endpoints/SQL (не дублируем).
model-tools — обёртки на расчётные движки (forecast, seasonality, эконом).

Каждый инструмент возвращает dict с полями:
- value/data: само число/структура
- source: 'api' | 'db_aggregate' | 'model' | 'estimated'
- contour: 'official' | 'operational' | None  (для финансовых)
- meta: пояснение, период, и т.д.

Принципы (Принципы Flowoi):
1. Зеркало Ozon: данные из тех же эндпоинтов что UI.
2. Два контура: P&L всегда указывает 'official'/'operational'.
4. source-флаг.
5. Прогноз/совет помечен 'estimated' в source.

OpenAI tool-schema (formatChat Completions):
  {type: 'function', function: {name, description, parameters: JSONSchema}}
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ============================================================
# DATA-TOOLS
# ============================================================


async def get_metrics(
    db: AsyncSession, company_id: uuid.UUID, *,
    cabinet_id: str | None = None,
    product_id: str | None = None,
    period_from: str | None = None,
    period_to: str | None = None,
    metrics: list[str] | None = None,
) -> dict:
    """Дневные метрики по выбранным товарам/кабинету/периоду."""
    metrics = metrics or ["impressions", "orders", "delivered", "revenue"]
    df = date.fromisoformat(period_from) if period_from else (date.today() - timedelta(days=30))
    dt = date.fromisoformat(period_to) if period_to else date.today()

    where = ["p.is_archived = false", "oa.company_id = :cid", "ad.date >= :df", "ad.date <= :dt"]
    params: dict = {"cid": str(company_id), "df": df, "dt": dt}
    if cabinet_id:
        where.append("oa.id = :cab")
        params["cab"] = cabinet_id
    if product_id:
        where.append("p.id = :pid")
        params["pid"] = product_id

    rows = (await db.execute(text(f"""
        SELECT ad.date,
               SUM(COALESCE(ad.hits_view, ad.hits_view_search + ad.hits_view_pdp))::int AS impressions,
               SUM(ad.ordered_units)::int   AS orders,
               SUM(ad.delivered_units)::int AS delivered,
               SUM(ad.revenue)::float        AS revenue,
               SUM(ad.hits_tocart_search + ad.hits_tocart_pdp)::int AS to_cart
        FROM analytics_daily ad
        JOIN products p ON p.id = ad.product_id
        JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
        WHERE {' AND '.join(where)}
        GROUP BY ad.date ORDER BY ad.date
    """), params)).all()
    return {
        "source": "db_aggregate",
        "period": {"from": df.isoformat(), "to": dt.isoformat()},
        "filters": {"cabinet_id": cabinet_id, "product_id": product_id},
        "metrics": metrics,
        "rows": [
            {"date": r.date.isoformat(), "impressions": r.impressions or 0,
             "orders": r.orders or 0, "delivered": r.delivered or 0,
             "revenue": float(r.revenue or 0), "to_cart": r.to_cart or 0}
            for r in rows
        ],
    }


async def get_pnl(
    db: AsyncSession, company_id: uuid.UUID, *,
    cabinet_id: str | None = None,
    period_from: str | None = None,
    period_to: str | None = None,
    model: str = "operational",
) -> dict:
    """
    P&L с явным указанием контура.
    model='operational' → наша оперативная модель (Transaction.accruals_for_sale)
    model='official'    → официальный отчёт Ozon (Realization)
    """
    df = date.fromisoformat(period_from) if period_from else (date.today() - timedelta(days=30))
    dt = date.fromisoformat(period_to) if period_to else date.today()

    if model not in ("operational", "official"):
        return {"error": f"model must be 'operational' or 'official', got {model}"}

    where = ["oa.company_id = :cid", "t.operation_date >= :df", "t.operation_date <= :dt"]
    params: dict = {"cid": str(company_id), "df": df, "dt": dt}
    if cabinet_id:
        where.append("oa.id = :cab")
        params["cab"] = cabinet_id

    r = (await db.execute(text(f"""
        SELECT
            COALESCE(SUM(t.accruals_for_sale) FILTER (WHERE t.operation_type='OperationAgentDeliveredToCustomer'), 0)::float AS seller_revenue,
            COALESCE(SUM(ABS(t.sale_commission)), 0)::float AS commissions,
            COALESCE(SUM(ABS(t.delivery_to_customer)), 0)::float AS logistics,
            COALESCE(SUM(ABS(t.storage)), 0)::float AS storage,
            COALESCE(SUM(ABS(t.acquiring)), 0)::float AS acquiring,
            COALESCE(SUM(ABS(t.advertising)), 0)::float AS advertising,
            COALESCE(SUM(ABS(t.return_logistics)), 0)::float AS return_logistics,
            COALESCE(SUM(ABS(t.last_mile)), 0)::float AS last_mile
        FROM transactions t
        JOIN ozon_accounts oa ON oa.id = t.ozon_account_id
        WHERE {' AND '.join(where)}
    """), params)).first()

    seller_revenue = float(r.seller_revenue or 0)
    expenses = sum(float(getattr(r, k) or 0) for k in (
        "commissions", "logistics", "storage", "acquiring", "advertising",
        "return_logistics", "last_mile",
    ))
    return {
        "source": "db_aggregate",
        "contour": model,
        "period": {"from": df.isoformat(), "to": dt.isoformat()},
        "filters": {"cabinet_id": cabinet_id},
        "seller_revenue_rub": round(seller_revenue, 2),
        "expenses_breakdown": {
            "commissions": round(float(r.commissions or 0), 2),
            "logistics": round(float(r.logistics or 0), 2),
            "storage": round(float(r.storage or 0), 2),
            "acquiring": round(float(r.acquiring or 0), 2),
            "advertising": round(float(r.advertising or 0), 2),
            "return_logistics": round(float(r.return_logistics or 0), 2),
            "last_mile": round(float(r.last_mile or 0), 2),
        },
        "expenses_total_rub": round(expenses, 2),
        "gross_profit_rub": round(seller_revenue - expenses, 2),
        "note": (
            "seller_revenue = accruals_for_sale (Выручка + Баллы + Программы партнёров)."
            " Контур: " + model + ". COGS и налог НЕ включены."
        ),
    }


async def get_funnel(
    db: AsyncSession, company_id: uuid.UUID, *,
    cabinet_id: str | None = None,
    product_id: str | None = None,
    period_from: str | None = None,
    period_to: str | None = None,
) -> dict:
    """Воронка: показы → корзина → заказ → выкуп + конверсии."""
    df = date.fromisoformat(period_from) if period_from else (date.today() - timedelta(days=30))
    dt = date.fromisoformat(period_to) if period_to else date.today()
    where = ["p.is_archived = false", "oa.company_id = :cid", "ad.date >= :df", "ad.date <= :dt"]
    params: dict = {"cid": str(company_id), "df": df, "dt": dt}
    if cabinet_id:
        where.append("oa.id = :cab"); params["cab"] = cabinet_id
    if product_id:
        where.append("p.id = :pid"); params["pid"] = product_id

    r = (await db.execute(text(f"""
        SELECT
            SUM(COALESCE(ad.hits_view, ad.hits_view_search + ad.hits_view_pdp))::int AS impressions,
            SUM(ad.session_view_pdp)::int AS card_visits,
            SUM(ad.hits_tocart_search + ad.hits_tocart_pdp)::int AS to_cart,
            SUM(ad.ordered_units)::int    AS orders,
            SUM(ad.delivered_units)::int  AS delivered,
            SUM(ad.revenue)::float        AS revenue
        FROM analytics_daily ad
        JOIN products p ON p.id = ad.product_id
        JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
        WHERE {' AND '.join(where)}
    """), params)).first()

    imp = r.impressions or 0
    cv = r.card_visits or 0
    tc = r.to_cart or 0
    ord_ = r.orders or 0
    dlv = r.delivered or 0

    def pct(num, den):
        return round(num / den * 100, 2) if den else None

    return {
        "source": "db_aggregate",
        "period": {"from": df.isoformat(), "to": dt.isoformat()},
        "filters": {"cabinet_id": cabinet_id, "product_id": product_id},
        "impressions": imp, "card_visits": cv, "to_cart": tc,
        "orders": ord_, "delivered": dlv, "revenue_rub": round(float(r.revenue or 0), 2),
        "conversions": {
            "imp_to_card_pct": pct(cv, imp),
            "card_to_cart_pct": pct(tc, cv),
            "cart_to_order_pct": pct(ord_, tc),
            "order_to_delivered_pct": pct(dlv, ord_),
            "overall_pct": round(dlv / imp * 100, 4) if imp else None,
        },
    }


async def get_stock(
    db: AsyncSession, company_id: uuid.UUID, *,
    cabinet_id: str | None = None,
    product_id: str | None = None,
) -> dict:
    """Текущий остаток + дни запаса по скорости продаж за 30 дней."""
    where = ["p.is_archived = false", "oa.company_id = :cid"]
    params: dict = {"cid": str(company_id)}
    if cabinet_id:
        where.append("oa.id = :cab"); params["cab"] = cabinet_id
    if product_id:
        where.append("p.id = :pid"); params["pid"] = product_id

    rows = (await db.execute(text(f"""
        WITH last_wh AS (
            SELECT product_id, MAX(time) t FROM stocks
            WHERE warehouse_type='FBO_WH' AND time > NOW() - INTERVAL '7 days'
            GROUP BY product_id
        ),
        last_agg AS (
            SELECT product_id, MAX(time) t FROM stocks
            WHERE warehouse_type IN ('AGG','FBO','FBS','RFBS')
              AND time > NOW() - INTERVAL '7 days'
            GROUP BY product_id
        ),
        wh_sum AS (
            SELECT s.product_id, COALESCE(SUM(GREATEST(s.free_to_sell - s.reserved, 0)),0)::int AS total
            FROM stocks s JOIN last_wh l ON l.product_id=s.product_id AND l.t=s.time
            WHERE s.warehouse_type='FBO_WH' GROUP BY s.product_id
        ),
        agg_sum AS (
            SELECT s.product_id, COALESCE(SUM(GREATEST(s.free_to_sell - s.reserved, 0)),0)::int AS total
            FROM stocks s JOIN last_agg l ON l.product_id=s.product_id AND l.t=s.time
            WHERE s.warehouse_type IN ('FBS','RFBS')
               OR (s.warehouse_type IN ('AGG','FBO') AND NOT EXISTS (
                    SELECT 1 FROM last_wh w WHERE w.product_id=s.product_id))
            GROUP BY s.product_id
        ),
        velocity AS (
            SELECT oi.product_id,
                   SUM(oi.quantity) FILTER (WHERE o.status='delivered')::float / 30 AS daily
            FROM order_items oi JOIN orders o ON o.id = oi.order_id
            WHERE o.order_created_at >= NOW() - INTERVAL '30 days'
            GROUP BY oi.product_id
        )
        SELECT p.id::text id, p.name, p.offer_id, p.ozon_sku,
               oa.name AS cabinet,
               (COALESCE(wh.total, 0) + COALESCE(ag.total, 0))::int AS stock,
               COALESCE(v.daily, 0)::float AS daily_sales
        FROM products p
        JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
        LEFT JOIN wh_sum wh ON wh.product_id = p.id
        LEFT JOIN agg_sum ag ON ag.product_id = p.id
        LEFT JOIN velocity v ON v.product_id = p.id
        WHERE {' AND '.join(where)}
        ORDER BY p.name
    """), params)).all()
    items = []
    for r in rows:
        doi = (r.stock / r.daily_sales) if r.daily_sales and r.daily_sales > 0 else None
        items.append({
            "product_id": r.id, "name": r.name,
            "offer_id": r.offer_id, "ozon_sku": r.ozon_sku,
            "cabinet": r.cabinet, "stock": r.stock,
            "daily_sales_avg": round(r.daily_sales, 2) if r.daily_sales > 0 else 0,
            "days_of_inventory": round(doi, 1) if doi else None,
        })
    return {"source": "db_aggregate", "items": items}


async def get_price(
    db: AsyncSession, company_id: uuid.UUID, *, product_id: str,
) -> dict:
    """Цена продавца, покупателя, СПП, комиссия."""
    r = (await db.execute(text("""
        SELECT p.id::text id, p.name, p.offer_id, p.ozon_sku,
               p.current_price, p.marketing_price, p.selling_price,
               p.avg_customer_price_30d, p.min_price, p.price_index,
               p.cost_price
        FROM products p
        JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
        WHERE p.id = :pid AND oa.company_id = :cid
    """), {"pid": product_id, "cid": str(company_id)})).first()
    if not r:
        return {"error": "Товар не найден"}

    seller = float(r.marketing_price or r.selling_price or r.current_price or 0)
    customer = float(r.avg_customer_price_30d or 0)
    spp_pct = ((seller - customer) / seller * 100) if (seller and customer) else None
    return {
        "source": "api",
        "product_id": r.id, "name": r.name, "offer_id": r.offer_id,
        "seller_price_rub": seller,
        "customer_avg_price_30d_rub": customer or None,
        "min_price_rub": float(r.min_price) if r.min_price else None,
        "current_price_rub": float(r.current_price) if r.current_price else None,
        "spp_estimate_pct": round(spp_pct, 1) if spp_pct is not None else None,
        "cost_price_rub": float(r.cost_price) if r.cost_price else None,
        "price_index": float(r.price_index) if r.price_index else None,
        "note": "seller_price = marketing_seller_price (НЕ маркетинговая зачёркнутая). "
                "customer_avg_price_30d — средняя 'оплачено покупателем' за 30 дней.",
    }


# ============================================================
# MODEL-TOOLS — детерминированные расчёты
# ============================================================


async def unit_economics(
    db: AsyncSession, company_id: uuid.UUID, *,
    product_id: str, price: float | None = None,
) -> dict:
    """Юнит-экономика при цене (default = текущая marketing_seller_price)."""
    p = (await db.execute(text("""
        SELECT p.id::text id, p.name, p.cost_price, p.marketing_price,
               p.selling_price, p.current_price
        FROM products p JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
        WHERE p.id = :pid AND oa.company_id = :cid
    """), {"pid": product_id, "cid": str(company_id)})).first()
    if not p:
        return {"error": "Товар не найден"}

    seller = float(price or p.marketing_price or p.selling_price or p.current_price or 0)
    cost = float(p.cost_price or 0)
    if not seller:
        return {"error": "Нет цены продавца"}

    # Источник коэффициентов — services/finance_consts.py (единая константа,
    # 41% было исторической ОШИБКОЙ из старого reconcile_realization).
    from app.services.finance_consts import (
        DEFAULT_COMMISSION_PCT, ACQUIRING_PCT_DEFAULT, LOGISTICS_PER_UNIT_DEFAULT,
    )
    comm_pct = DEFAULT_COMMISSION_PCT / 100  # 25%
    acq_pct = ACQUIRING_PCT_DEFAULT / 100    # 1.5%
    commission = seller * comm_pct
    acquiring = seller * acq_pct
    logistics = LOGISTICS_PER_UNIT_DEFAULT  # ₽/шт, не %
    mp_costs = commission + acquiring + logistics
    margin_before_cogs = seller - mp_costs
    margin = margin_before_cogs - cost if cost else None
    margin_pct = (margin / seller * 100) if (margin is not None and seller) else None
    return {
        "source": "model",
        "estimated": True,
        "product_id": p.id, "name": p.name,
        "price_rub": round(seller, 2),
        "cost_rub": round(cost, 2) if cost else None,
        "mp_costs_estimates": {
            "commission_pct": comm_pct * 100,
            "acquiring_pct": acq_pct * 100,
            "logistics_rub_per_unit": LOGISTICS_PER_UNIT_DEFAULT,
        },
        "mp_costs_total_rub": round(mp_costs, 2),
        "margin_before_cogs_rub": round(margin_before_cogs, 2),
        "margin_after_cogs_rub": round(margin, 2) if margin is not None else None,
        "margin_pct": round(margin_pct, 2) if margin_pct is not None else None,
        "note": "Оценка по средним долям Ozon. Точно — через get_pnl(operational).",
    }


async def demand_forecast(
    db: AsyncSession, company_id: uuid.UUID, *,
    product_id: str, horizon_months: int = 3,
) -> dict:
    """Прогноз продаж на N месяцев — обёртка на seasonality.source_a.forecast_peak."""
    from app.services.seasonality import source_a
    p = (await db.execute(text("""
        SELECT p.id::text FROM products p
        JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
        WHERE p.id = :pid AND oa.company_id = :cid
    """), {"pid": product_id, "cid": str(company_id)})).first()
    if not p:
        return {"error": "Товар не найден"}

    data = await source_a.forecast_peak(
        db, product_id=uuid.UUID(product_id),
        metric="buyouts", horizon_months=horizon_months,
    )
    return {
        "source": "model",
        "estimated": True,
        "confidence": data.get("confidence"),
        "note": data.get("note"),
        "base_monthly_units": data.get("base_monthly"),
        "rows": data.get("rows", []),
        "method": "seasonal_index × avg_daily_last_90_days × 30",
    }


async def elasticity(
    db: AsyncSession, company_id: uuid.UUID, *,
    product_id: str,
) -> dict:
    """Эластичность цена→спрос. MVP: рассчитываем по последним 90 дням
    через корреляцию ln(price) ↔ ln(quantity)."""
    # Тянем дневные данные за 90 дней
    rows = (await db.execute(text("""
        SELECT DATE(o.order_created_at) AS d,
               AVG(oi.price)::float AS avg_price,
               SUM(oi.quantity) FILTER (WHERE o.status='delivered')::int AS qty
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
        WHERE p.id = :pid AND oa.company_id = :cid
          AND o.order_created_at >= NOW() - INTERVAL '90 days'
          AND oi.price > 0
        GROUP BY DATE(o.order_created_at)
        HAVING SUM(oi.quantity) FILTER (WHERE o.status='delivered') > 0
    """), {"pid": product_id, "cid": str(company_id)})).all()

    if len(rows) < 10:
        return {
            "source": "model", "estimated": True,
            "elasticity": None, "r_squared": None,
            "note": f"Недостаточно данных ({len(rows)} дней с продажами, нужно ≥10).",
        }
    import math
    xs = [math.log(r.avg_price) for r in rows]
    ys = [math.log(r.qty) for r in rows]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((xs[i]-mean_x) * (ys[i]-mean_y) for i in range(n))
    den_x = sum((x-mean_x)**2 for x in xs)
    den_y = sum((y-mean_y)**2 for y in ys)
    if den_x == 0 or den_y == 0:
        return {"source": "model", "estimated": True, "elasticity": None,
                "r_squared": None, "note": "Нет дисперсии цены или спроса."}
    slope = num / den_x
    r = num / (math.sqrt(den_x) * math.sqrt(den_y))
    return {
        "source": "model", "estimated": True,
        "elasticity": round(slope, 3),
        "r_squared": round(r * r, 3),
        "days_in_model": n,
        "interpretation": (
            f"Эластичность {slope:.2f}: +1% к цене ≈ {slope:+.2f}% к спросу. "
            f"R²={r*r:.2f} (1.0 = идеальная связь, <0.3 = шум)."
        ),
        "note": "Расчёт по последним 90 дням, log-log регрессия. "
                "Чем меньше дисперсия цены — тем шире доверительный интервал.",
    }


async def keep_or_drop(
    db: AsyncSession, company_id: uuid.UUID, *,
    product_id: str,
) -> dict:
    """Модель «держать или вывести»: маржа × оборачиваемость × хранение."""
    p = (await db.execute(text("""
        SELECT p.id::text id, p.name, p.ozon_account_id::text cab_id
        FROM products p JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
        WHERE p.id = :pid AND oa.company_id = :cid
    """), {"pid": product_id, "cid": str(company_id)})).first()
    if not p:
        return {"error": "Товар не найден"}

    # Stock + velocity + storage 30d
    s = (await db.execute(text("""
        WITH stock AS (
            SELECT SUM(GREATEST(free_to_sell - reserved, 0))::int AS qty
            FROM stocks WHERE product_id = :pid AND time > NOW() - INTERVAL '7 days'
        ),
        velocity AS (
            SELECT SUM(oi.quantity) FILTER (WHERE o.status='delivered')::float / 30 AS daily
            FROM order_items oi JOIN orders o ON o.id = oi.order_id
            WHERE oi.product_id = :pid AND o.order_created_at >= NOW() - INTERVAL '30 days'
        ),
        rev AS (
            SELECT COALESCE(SUM(oi.price * oi.quantity) FILTER (WHERE o.status='delivered'),0)::float AS amount
            FROM order_items oi JOIN orders o ON o.id = oi.order_id
            WHERE oi.product_id = :pid AND o.order_created_at >= NOW() - INTERVAL '30 days'
        ),
        storage AS (
            SELECT COALESCE(SUM(ABS(ps.storage_cost)),0)::float AS amount
            FROM placement_storage_daily ps
            WHERE ps.cabinet_id = :cab
              AND ps.sku IN (SELECT DISTINCT ozon_sku FROM order_items WHERE product_id = :pid AND ozon_sku > 0)
              AND ps.day >= CURRENT_DATE - INTERVAL '30 days'
        )
        SELECT (SELECT qty FROM stock) stock,
               (SELECT daily FROM velocity) daily,
               (SELECT amount FROM rev) revenue,
               (SELECT amount FROM storage) storage
    """), {"pid": product_id, "cab": p.cab_id})).first()

    stock = int(s.stock or 0)
    daily = float(s.daily or 0)
    revenue = float(s.revenue or 0)
    storage = float(s.storage or 0)

    doi = (stock / daily) if daily > 0 else None
    storage_share = (storage / revenue) if revenue > 0 else None

    verdict = "keep"
    reasons = []

    if daily < 0.1 and stock > 0:
        verdict = "drop"
        reasons.append(f"Скорость {daily:.2f} продаж/день < 0.1 (мёртвый сток).")
    elif doi is not None and doi > 120:
        verdict = "drop"
        reasons.append(f"Запас на {doi:.0f} дней — критически много.")
    elif storage_share is not None and storage_share > 0.20:
        verdict = "drop"
        reasons.append(f"Хранение съедает {storage_share*100:.1f}% выручки.")
    elif doi is not None and doi > 60:
        verdict = "watch"
        reasons.append(f"Запас на {doi:.0f} дней — стоит уменьшить дозаказ.")
    elif storage_share is not None and storage_share > 0.05:
        verdict = "watch"
        reasons.append(f"Хранение {storage_share*100:.1f}% выручки (>5% — следить).")
    else:
        reasons.append("Запас и хранение в норме.")

    return {
        "source": "model", "estimated": True,
        "product_id": p.id, "name": p.name,
        "verdict": verdict,  # 'keep' | 'watch' | 'drop'
        "reasons": reasons,
        "metrics": {
            "stock": stock, "daily_sales": round(daily, 2),
            "days_of_inventory": round(doi, 1) if doi else None,
            "revenue_30d_rub": round(revenue, 2),
            "storage_30d_rub": round(storage, 2),
            "storage_share_pct": round(storage_share * 100, 2) if storage_share else None,
        },
        "note": "Пороги: dead<0.1/day, doi>120 → drop; doi>60 или storage_share>5% → watch.",
    }


async def price_optimizer(
    db: AsyncSession, company_id: uuid.UUID, *,
    product_id: str, search_range_pct: float = 20,
) -> dict:
    """Найти цену максимизирующую прибыль по кривой эластичности.

    MVP: используем log-log эластичность из elasticity() →
      qty(p) = qty0 × (p/p0)^E
      profit(p) = qty(p) × (p - cost - mp_costs(p))
    Ищем максимум на сетке цен ±search_range_pct.
    """
    el = await elasticity(db, company_id, product_id=product_id)
    if el.get("elasticity") is None:
        return {"source": "model", "error": el.get("note") or "Эластичность не рассчитана."}

    ue = await unit_economics(db, company_id, product_id=product_id)
    if "error" in ue:
        return {"source": "model", "error": ue["error"]}
    cost = ue.get("cost_rub") or 0
    p0 = ue["price_rub"]
    E = el["elasticity"]

    # Получаем средний daily на текущей цене
    s = (await db.execute(text("""
        SELECT SUM(oi.quantity) FILTER (WHERE o.status='delivered')::float / 30 AS daily
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE oi.product_id = :pid AND o.order_created_at >= NOW() - INTERVAL '30 days'
    """), {"pid": product_id})).first()
    qty0 = float(s.daily or 0) * 30  # месячный
    if qty0 <= 0:
        return {"source": "model", "error": "Нет продаж за 30 дней — оптимизация невозможна."}

    # mp_costs_pct ≈ 52.5% (из unit_economics) — переменная от цены
    mp_pct = (ue["mp_costs_total_rub"] / p0) if p0 else 0.525

    best = {"price": p0, "qty": qty0, "profit": (p0 - cost - p0 * mp_pct) * qty0}
    grid = []
    for pct_change in range(-int(search_range_pct), int(search_range_pct) + 1, 2):
        p = p0 * (1 + pct_change / 100)
        # qty: q = qty0 × (p/p0)^E
        qty = qty0 * ((p / p0) ** E) if p > 0 else 0
        if qty <= 0:
            continue
        margin_per_unit = p - cost - p * mp_pct
        profit = qty * margin_per_unit
        grid.append({
            "price": round(p, 2), "qty_monthly": round(qty, 1),
            "margin_per_unit_rub": round(margin_per_unit, 2),
            "profit_monthly_rub": round(profit, 2),
            "delta_pct": pct_change,
        })
        if profit > best["profit"]:
            best = {"price": p, "qty": qty, "profit": profit, "delta_pct": pct_change}

    return {
        "source": "model", "estimated": True,
        "current_price_rub": round(p0, 2),
        "elasticity": E, "r_squared": el["r_squared"],
        "optimal_price_rub": round(best["price"], 2),
        "optimal_change_pct": best.get("delta_pct", 0),
        "expected_qty_monthly": round(best["qty"], 1),
        "expected_profit_monthly_rub": round(best["profit"], 2),
        "grid": grid,
        "note": (
            "MVP: log-log эластичность + средняя mp_costs за 30 дней. "
            "Низкий R² = шум; рекомендация осторожно. "
            "Реальный buyer-experience СПП может сдвинуть кривую."
        ),
    }


# ============================================================
# REGISTRY (OpenAI format)
# ============================================================


TOOLS_V2: dict[str, dict] = {
    # ─── data-tools ───
    "get_metrics": {
        "fn": get_metrics,
        "spec": {
            "name": "get_metrics",
            "description": (
                "Дневные метрики Ozon analytics_daily: показы, заказы, выкуп, выручка, корзины. "
                "Фильтры по кабинету и/или товару + период."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cabinet_id": {"type": "string", "description": "UUID кабинета (опц.)"},
                    "product_id": {"type": "string", "description": "UUID товара (опц.)"},
                    "period_from": {"type": "string", "description": "YYYY-MM-DD"},
                    "period_to": {"type": "string", "description": "YYYY-MM-DD"},
                    "metrics": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
    "get_pnl": {
        "fn": get_pnl,
        "spec": {
            "name": "get_pnl",
            "description": (
                "P&L с явным контуром. ОБЯЗАТЕЛЬНО указать model='operational' "
                "(наша оперативная модель из transactions) или 'official' (отчёт Ozon)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cabinet_id": {"type": "string"},
                    "period_from": {"type": "string"},
                    "period_to": {"type": "string"},
                    "model": {"type": "string", "enum": ["operational", "official"], "default": "operational"},
                },
                "required": ["model"],
            },
        },
    },
    "get_funnel": {
        "fn": get_funnel,
        "spec": {
            "name": "get_funnel",
            "description": "Воронка показы→корзина→заказ→выкуп с конверсиями.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cabinet_id": {"type": "string"},
                    "product_id": {"type": "string"},
                    "period_from": {"type": "string"},
                    "period_to": {"type": "string"},
                },
            },
        },
    },
    "get_stock": {
        "fn": get_stock,
        "spec": {
            "name": "get_stock",
            "description": "Текущий остаток + дни запаса. Фильтры по кабинету/товару.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cabinet_id": {"type": "string"},
                    "product_id": {"type": "string"},
                },
            },
        },
    },
    "get_price": {
        "fn": get_price,
        "spec": {
            "name": "get_price",
            "description": "Цена продавца, средняя цена покупателя (с СПП), оценка СПП%.",
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "string"}},
                "required": ["product_id"],
            },
        },
    },
    # ─── model-tools ───
    "unit_economics": {
        "fn": unit_economics,
        "spec": {
            "name": "unit_economics",
            "description": (
                "Юнит-экономика SKU при заданной цене (default — текущая seller_price). "
                "Возвращает маржу до и после COGS, % затрат МП. Помечено 'estimated'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "price": {"type": "number", "description": "Цена ₽ (опц.)"},
                },
                "required": ["product_id"],
            },
        },
    },
    "demand_forecast": {
        "fn": demand_forecast,
        "spec": {
            "name": "demand_forecast",
            "description": (
                "Прогноз спроса на N месяцев по сезонному индексу × avg_daily_last_90д. "
                "Помечено 'estimated'. Без истории ≥90 дней — пусто."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "horizon_months": {"type": "integer", "default": 3},
                },
                "required": ["product_id"],
            },
        },
    },
    "elasticity": {
        "fn": elasticity,
        "spec": {
            "name": "elasticity",
            "description": (
                "Эластичность цена→спрос по log-log регрессии за 90 дней. "
                "Возвращает E + R². E≈0 = неэластично, E=-2 = сильно реагирует."
            ),
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "string"}},
                "required": ["product_id"],
            },
        },
    },
    "keep_or_drop": {
        "fn": keep_or_drop,
        "spec": {
            "name": "keep_or_drop",
            "description": (
                "Модель «держать или вывести»: маржа × оборачиваемость × расход на хранение. "
                "Вердикт: keep | watch | drop + аргументы."
            ),
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "string"}},
                "required": ["product_id"],
            },
        },
    },
    "price_optimizer": {
        "fn": price_optimizer,
        "spec": {
            "name": "price_optimizer",
            "description": (
                "Находит цену, максимизирующую месячную прибыль по кривой эластичности. "
                "Возвращает optimal_price + сетку профита. Низкий R² = шум."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "search_range_pct": {"type": "number", "default": 20},
                },
                "required": ["product_id"],
            },
        },
    },
}


def openai_tool_specs() -> list[dict]:
    """OpenAI tool-schema формат."""
    return [{"type": "function", "function": t["spec"]} for t in TOOLS_V2.values()]


async def execute_tool(
    name: str, args: dict, db: AsyncSession, company_id: uuid.UUID,
) -> dict:
    """Исполнить tool-call. Ловим все исключения, чтобы не падал loop."""
    entry = TOOLS_V2.get(name)
    if not entry:
        return {"error": f"Unknown tool: {name}"}
    try:
        return await entry["fn"](db, company_id, **(args or {}))
    except TypeError as e:
        return {"error": f"Bad arguments: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"Tool failed: {type(e).__name__}: {e}"}
