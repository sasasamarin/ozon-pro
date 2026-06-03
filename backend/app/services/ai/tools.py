"""
AI Tools — функции, которые LLM может вызывать через function calling.

Каждая функция:
- получает (db, company_id, **params)
- возвращает dict — данные для LLM

LLM сам решает что вызвать. Мы НЕ навязываем порядок — это убирает
hardcoded routing «если в вопросе слово X — звать Y» (хрупкий подход).

Принципы (Flowoi):
- #4: source-флаг на каждое число (api/xlsx/estimated/manual/missing)
- #5: оценки помечены — LLM скажет «оценка ~5к ₽» вместо «5043.21 ₽»
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ============================================================
# 1. Сводка по продажам / выручке
# ============================================================


async def get_revenue_summary(
    db: AsyncSession, company_id: uuid.UUID, days: int = 30,
) -> dict:
    """Сводка выручки за период по всем кабинетам компании."""
    df = date.today() - timedelta(days=days)
    rows = (await db.execute(text("""
        SELECT
            oa.name AS cabinet,
            COALESCE(SUM(oi.price * oi.quantity), 0)::float AS ordered_value,
            COALESCE(SUM(oi.price * oi.quantity) FILTER (WHERE o.status='delivered'), 0)::float AS delivered_value,
            COUNT(DISTINCT o.id) AS orders,
            COUNT(DISTINCT o.id) FILTER (WHERE o.status='delivered') AS delivered,
            COUNT(DISTINCT oi.product_id) AS skus
        FROM ozon_accounts oa
        LEFT JOIN orders o ON o.ozon_account_id = oa.id
            AND o.order_created_at >= :df
        LEFT JOIN order_items oi ON oi.order_id = o.id
        WHERE oa.company_id = :cid AND oa.deleted_at IS NULL
        GROUP BY oa.id, oa.name
        ORDER BY delivered_value DESC
    """), {"cid": str(company_id), "df": df})).all()

    # Seller revenue (с Баллами+Партнёрами) из transactions
    sr_rows = (await db.execute(text("""
        SELECT
            oa.name AS cabinet,
            COALESCE(SUM(t.accruals_for_sale), 0)::float AS seller_revenue
        FROM ozon_accounts oa
        LEFT JOIN transactions t ON t.ozon_account_id = oa.id
            AND t.operation_date >= :df
            AND t.operation_type = 'OperationAgentDeliveredToCustomer'
        WHERE oa.company_id = :cid AND oa.deleted_at IS NULL
        GROUP BY oa.name
    """), {"cid": str(company_id), "df": df})).all()
    sr_by_cab = {r.cabinet: float(r.seller_revenue or 0) for r in sr_rows}

    cabinets = [
        {
            "cabinet": r.cabinet,
            "ordered_amount_rub": round(r.ordered_value, 2),
            "delivered_amount_rub": round(r.delivered_value, 2),
            "seller_revenue_rub": round(sr_by_cab.get(r.cabinet, 0), 2),
            "orders_total": r.orders,
            "orders_delivered": r.delivered,
            "active_skus": r.skus,
        }
        for r in rows
    ]
    return {
        "period_days": days,
        "period_from": df.isoformat(),
        "cabinets": cabinets,
        "total_seller_revenue_rub": round(sum(c["seller_revenue_rub"] for c in cabinets), 2),
        "total_delivered_amount_rub": round(sum(c["delivered_amount_rub"] for c in cabinets), 2),
        "total_orders_delivered": sum(c["orders_delivered"] for c in cabinets),
        "note": (
            "seller_revenue_rub — что Ozon начислил продавцу (Выручка + Баллы + "
            "Программы партнёров) — главная цифра для P&L и налога."
        ),
    }


# ============================================================
# 2. Stockouts / запас
# ============================================================


async def get_stockouts(
    db: AsyncSession, company_id: uuid.UUID, threshold_days: int = 14,
) -> dict:
    """Товары которые скоро закончатся — остаток / скорость продаж < threshold."""
    rows = (await db.execute(text("""
        WITH last_stock AS (
            SELECT product_id,
                   SUM(GREATEST(free_to_sell - reserved, 0)) AS stock
            FROM stocks
            WHERE time > NOW() - INTERVAL '2 days'
              AND warehouse_type IN ('AGG','FBO','FBO_WH','FBS','RFBS')
            GROUP BY product_id
        ),
        velocity AS (
            SELECT oi.product_id,
                   COUNT(*) FILTER (WHERE o.status='delivered')::float / 30 AS daily_sales
            FROM order_items oi JOIN orders o ON o.id = oi.order_id
            WHERE o.order_created_at >= NOW() - INTERVAL '30 days'
            GROUP BY oi.product_id
        )
        SELECT p.id::text, p.name, p.offer_id, p.ozon_sku,
               COALESCE(ls.stock, 0)::int AS stock,
               COALESCE(v.daily_sales, 0)::float AS daily_sales,
               CASE WHEN v.daily_sales > 0
                    THEN COALESCE(ls.stock, 0) / v.daily_sales
                    ELSE NULL END::float AS days_left
        FROM products p
        JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
        LEFT JOIN last_stock ls ON ls.product_id = p.id
        LEFT JOIN velocity v ON v.product_id = p.id
        WHERE oa.company_id = :cid AND p.is_archived = false
          AND v.daily_sales > 0
          AND COALESCE(ls.stock, 0) / NULLIF(v.daily_sales, 0) < :th
        ORDER BY days_left ASC NULLS LAST LIMIT 20
    """), {"cid": str(company_id), "th": threshold_days})).all()
    items = [
        {
            "product_id": r.id, "name": r.name, "offer_id": r.offer_id,
            "ozon_sku": r.ozon_sku,
            "stock_units": r.stock,
            "daily_sales_avg": round(r.daily_sales, 2),
            "days_left": round(r.days_left, 1) if r.days_left else None,
        }
        for r in rows
    ]
    return {
        "threshold_days": threshold_days,
        "items_count": len(items),
        "items": items,
        "note": "days_left = текущий остаток / средние ежедневные продажи за 30 дней.",
    }


# ============================================================
# 3. Топ-маржа / топ-выручка по SKU
# ============================================================


async def get_top_products(
    db: AsyncSession, company_id: uuid.UUID,
    metric: str = "revenue", limit: int = 10, days: int = 30,
) -> dict:
    """Топ SKU по revenue / margin_pct / orders за период."""
    df = date.today() - timedelta(days=days)
    rows = (await db.execute(text("""
        SELECT p.id::text, p.name, p.offer_id, p.ozon_sku,
               COALESCE(p.cost_price, 0)::float AS cost,
               COALESCE(SUM(oi.price * oi.quantity) FILTER (WHERE o.status='delivered'), 0)::float AS revenue,
               COALESCE(SUM(oi.quantity) FILTER (WHERE o.status='delivered'), 0)::int AS units
        FROM products p
        JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
        LEFT JOIN order_items oi ON oi.product_id = p.id
        LEFT JOIN orders o ON o.id = oi.order_id AND o.order_created_at >= :df
        WHERE oa.company_id = :cid AND p.is_archived = false
        GROUP BY p.id, p.name, p.offer_id, p.ozon_sku, p.cost_price
        HAVING SUM(oi.quantity) FILTER (WHERE o.status='delivered') > 0
    """), {"cid": str(company_id), "df": df})).all()
    items = []
    for r in rows:
        revenue = float(r.revenue or 0)
        cogs = float(r.cost or 0) * (r.units or 0)
        margin_rub = revenue - cogs
        margin_pct = (margin_rub / revenue * 100) if revenue else None
        items.append({
            "product_id": r.id, "name": r.name, "offer_id": r.offer_id,
            "ozon_sku": r.ozon_sku, "revenue_rub": round(revenue, 2),
            "units_sold": r.units, "cost_per_unit_rub": round(r.cost, 2) if r.cost else None,
            "gross_margin_rub": round(margin_rub, 2),
            "gross_margin_pct": round(margin_pct, 1) if margin_pct is not None else None,
            "_cost_known": bool(r.cost and r.cost > 0),
        })
    # Сортировка
    if metric == "margin_pct":
        items = [i for i in items if i["gross_margin_pct"] is not None]
        items.sort(key=lambda x: x["gross_margin_pct"] or 0, reverse=True)
    elif metric == "units":
        items.sort(key=lambda x: x["units_sold"], reverse=True)
    else:  # revenue по дефолту
        items.sort(key=lambda x: x["revenue_rub"], reverse=True)
    return {
        "metric": metric, "period_days": days, "items": items[:limit],
        "note": "Маржа = revenue − cost_price × units. Без cost_price пометка _cost_known=false.",
    }


# ============================================================
# 4. Воронка SKU
# ============================================================


async def get_funnel_for_product(
    db: AsyncSession, company_id: uuid.UUID,
    product_id: str | uuid.UUID, days: int = 30,
) -> dict:
    """Воронка одного SKU: показы → клики → корзина → заказ → выкуп."""
    df = date.today() - timedelta(days=days)
    r = (await db.execute(text("""
        SELECT p.name,
               COALESCE(SUM(COALESCE(ad.hits_view, ad.hits_view_search+ad.hits_view_pdp)), 0)::int impressions,
               COALESCE(SUM(ad.session_view_pdp), 0)::int card_visits,
               COALESCE(SUM(ad.hits_tocart_search + ad.hits_tocart_pdp), 0)::int to_cart,
               COALESCE(SUM(ad.ordered_units), 0)::int orders,
               COALESCE(SUM(ad.delivered_units), 0)::int delivered,
               COALESCE(SUM(ad.revenue), 0)::float revenue
        FROM products p
        JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
        LEFT JOIN analytics_daily ad ON ad.product_id = p.id AND ad.date >= :df
        WHERE p.id = :pid AND oa.company_id = :cid
        GROUP BY p.name
    """), {"cid": str(company_id), "pid": str(product_id), "df": df})).first()
    if not r:
        return {"error": "Товар не найден или не вашего кабинета"}
    imp = r.impressions or 0
    visits = r.card_visits or 0
    cart = r.to_cart or 0
    orders = r.orders or 0
    deliv = r.delivered or 0
    return {
        "product_name": r.name, "period_days": days,
        "impressions": imp, "card_visits": visits, "to_cart": cart,
        "orders": orders, "delivered": deliv, "revenue_rub": round(float(r.revenue or 0), 2),
        "search_to_card_pct": round(visits/imp*100, 2) if imp else None,
        "card_to_cart_pct": round(cart/visits*100, 2) if visits else None,
        "cart_to_order_pct": round(orders/cart*100, 2) if cart else None,
        "delivery_pct": round(deliv/orders*100, 2) if orders else None,
        "overall_pct": round(deliv/imp*100, 4) if imp else None,
    }


# ============================================================
# 5. Сезонность SKU (использует Source A — свою историю)
# ============================================================


async def get_seasonality(
    db: AsyncSession, company_id: uuid.UUID,
    product_id: str | uuid.UUID, metric: str = "buyouts",
) -> dict:
    """Сезонный профиль SKU: индексы по месяцам + вердикт сезонный/ровный."""
    from app.services.seasonality import source_a
    p = (await db.execute(text("""
        SELECT p.id::text id, p.name, oa.id::text cab
        FROM products p JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
        WHERE p.id = :pid AND oa.company_id = :cid
    """), {"pid": str(product_id), "cid": str(company_id)})).first()
    if not p:
        return {"error": "Товар не найден"}

    pid = uuid.UUID(p.id)
    hs = await source_a.history_for_product(db, pid)
    if hs.days_history < 365:
        return {
            "product_name": p.name,
            "verdict": "insufficient",
            "days_history": hs.days_history,
            "note": hs.confidence_note,
        }
    prof = await source_a.profile(
        db, product_id=pid, metric=metric, granularity="month",  # type: ignore[arg-type]
    )
    indexes = [(b["bucket"], b["index"]) for b in prof["buckets"] if b["index"] is not None]
    if not indexes:
        return {"product_name": p.name, "verdict": "no_data"}
    by_idx = sorted(indexes, key=lambda x: x[1], reverse=True)
    peak_month = by_idx[0][0]
    low_month = by_idx[-1][0]
    amplitude = (by_idx[0][1] / by_idx[-1][1]) if by_idx[-1][1] else None
    months_ru = ["", "январь","февраль","март","апрель","май","июнь",
                 "июль","август","сентябрь","октябрь","ноябрь","декабрь"]
    return {
        "product_name": p.name, "days_history": hs.days_history,
        "verdict": "seasonal" if (amplitude and amplitude > 1.5) else "flat",
        "peak_month": months_ru[peak_month], "low_month": months_ru[low_month],
        "amplitude_ratio": round(amplitude, 2) if amplitude else None,
        "all_indexes_by_month": {months_ru[m]: round(i, 2) for m, i in indexes},
    }


# ============================================================
# 6. Список товаров кабинета — для поиска по имени/offer_id
# ============================================================


async def list_products(
    db: AsyncSession, company_id: uuid.UUID, search: str | None = None, limit: int = 30,
) -> dict:
    """Найти товары компании. search ищет по name / offer_id / ozon_sku."""
    params: dict[str, Any] = {"cid": str(company_id), "lim": limit}
    where = "oa.company_id = :cid AND p.is_archived = false"
    if search:
        params["q"] = f"%{search.lower()}%"
        where += (" AND (LOWER(p.name) LIKE :q OR LOWER(COALESCE(p.offer_id,'')) LIKE :q "
                  "OR CAST(p.ozon_sku AS TEXT) LIKE :q)")
    rows = (await db.execute(text(f"""
        SELECT p.id::text, p.name, p.offer_id, p.ozon_sku,
               oa.name AS cabinet
        FROM products p JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
        WHERE {where}
        ORDER BY p.name LIMIT :lim
    """), params)).all()
    return {
        "items": [
            {"product_id": r.id, "name": r.name, "offer_id": r.offer_id,
             "ozon_sku": r.ozon_sku, "cabinet": r.cabinet}
            for r in rows
        ]
    }


# ============================================================
# 7. P&L cводка
# ============================================================


async def get_pnl_summary(
    db: AsyncSession, company_id: uuid.UUID, days: int = 30,
) -> dict:
    """Сводный P&L по компании за период."""
    df = date.today() - timedelta(days=days)
    r = (await db.execute(text("""
        SELECT
            COALESCE(SUM(accruals_for_sale) FILTER (WHERE operation_type='OperationAgentDeliveredToCustomer'), 0)::float AS seller_revenue,
            COALESCE(SUM(ABS(sale_commission)), 0)::float AS commissions,
            COALESCE(SUM(ABS(delivery_to_customer)), 0)::float AS logistics,
            COALESCE(SUM(ABS(storage)), 0)::float AS storage,
            COALESCE(SUM(ABS(acquiring)), 0)::float AS acquiring,
            COALESCE(SUM(ABS(advertising)), 0)::float AS advertising,
            COALESCE(SUM(ABS(return_logistics)), 0)::float AS return_logistics
        FROM transactions t
        JOIN ozon_accounts oa ON oa.id = t.ozon_account_id
        WHERE oa.company_id = :cid AND t.operation_date >= :df
    """), {"cid": str(company_id), "df": df})).first()
    sr = float(r.seller_revenue or 0)
    expenses = sum(float(getattr(r, c) or 0) for c in (
        "commissions", "logistics", "storage", "acquiring", "advertising", "return_logistics"
    ))
    gross = sr - expenses
    return {
        "period_days": days, "period_from": df.isoformat(),
        "seller_revenue_rub": round(sr, 2),
        "expenses_breakdown": {
            "commissions": round(float(r.commissions or 0), 2),
            "logistics": round(float(r.logistics or 0), 2),
            "storage": round(float(r.storage or 0), 2),
            "acquiring": round(float(r.acquiring or 0), 2),
            "advertising": round(float(r.advertising or 0), 2),
            "return_logistics": round(float(r.return_logistics or 0), 2),
        },
        "expenses_total_rub": round(expenses, 2),
        "gross_profit_rub": round(gross, 2),
        "gross_profit_pct": round(gross / sr * 100, 2) if sr else None,
        "note": (
            "Без COGS и налога. Это валовая прибыль ДО себестоимости и налога УСН/ОСНО. "
            "seller_revenue включает Баллы и Программы партнёров."
        ),
    }


# ============================================================
# 8. Возвраты
# ============================================================


async def get_returns_summary(
    db: AsyncSession, company_id: uuid.UUID, days: int = 30,
) -> dict:
    """Возвраты + топ-возвращаемые SKU."""
    df = date.today() - timedelta(days=days)
    r = (await db.execute(text("""
        SELECT COUNT(*) cnt,
               COALESCE(SUM(return_amount), 0)::float total_amount
        FROM returns r JOIN ozon_accounts oa ON oa.id = r.ozon_account_id
        WHERE oa.company_id = :cid AND r.return_date >= :df
    """), {"cid": str(company_id), "df": df})).first()
    top = (await db.execute(text("""
        SELECT p.id::text, p.name, COUNT(*)::int cnt,
               COALESCE(SUM(r.return_amount), 0)::float total
        FROM returns r
        JOIN products p ON p.id = r.product_id
        JOIN ozon_accounts oa ON oa.id = r.ozon_account_id
        WHERE oa.company_id = :cid AND r.return_date >= :df
        GROUP BY p.id, p.name ORDER BY cnt DESC LIMIT 10
    """), {"cid": str(company_id), "df": df})).all()
    return {
        "period_days": days,
        "total_returns": r.cnt or 0,
        "total_refund_amount_rub": round(float(r.total_amount or 0), 2),
        "top_returned_skus": [
            {"product_id": x.id, "name": x.name, "count": x.cnt,
             "refund_amount_rub": round(float(x.total or 0), 2)}
            for x in top
        ],
    }


# ============================================================
# Registry — Anthropic tool schema + Python impl
# ============================================================


TOOL_REGISTRY: dict[str, dict] = {
    "get_revenue_summary": {
        "fn": get_revenue_summary,
        "schema": {
            "name": "get_revenue_summary",
            "description": (
                "Сводка выручки по всем кабинетам компании за период. "
                "Возвращает orders/delivered/seller_revenue по кабинетам + итоги. "
                "Включает Баллы и Программы партнёров (seller_revenue = главная цифра)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Глубина периода в днях. По умолчанию 30.",
                             "minimum": 1, "maximum": 730, "default": 30}
                },
            },
        },
    },
    "get_stockouts": {
        "fn": get_stockouts,
        "schema": {
            "name": "get_stockouts",
            "description": (
                "Товары с риском закончиться на складе. Возвращает SKU где "
                "остаток / средние ежедневные продажи < threshold_days. "
                "Использует ТОЛЬКО SKU со скоростью продаж > 0 (не мёртвый сток)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "threshold_days": {"type": "integer", "default": 14,
                                       "description": "При остатке менее N дней — попадает в список."}
                },
            },
        },
    },
    "get_top_products": {
        "fn": get_top_products,
        "schema": {
            "name": "get_top_products",
            "description": (
                "Топ SKU по выручке / марже / штукам. Только доставленные заказы. "
                "_cost_known=false значит себестоимость не задана и маржа = revenue (некорректно)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "enum": ["revenue", "margin_pct", "units"],
                               "default": "revenue"},
                    "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
                    "days": {"type": "integer", "default": 30, "minimum": 1, "maximum": 730},
                },
            },
        },
    },
    "get_funnel_for_product": {
        "fn": get_funnel_for_product,
        "schema": {
            "name": "get_funnel_for_product",
            "description": "Воронка одного SKU: показы → клики → корзина → заказ → выкуп.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "UUID товара"},
                    "days": {"type": "integer", "default": 30, "minimum": 1, "maximum": 365},
                },
                "required": ["product_id"],
            },
        },
    },
    "get_seasonality": {
        "fn": get_seasonality,
        "schema": {
            "name": "get_seasonality",
            "description": (
                "Сезонность SKU (по своим продажам). Возвращает вердикт seasonal/flat/insufficient + "
                "месяц пика. Требует ≥365 дней истории, иначе insufficient."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "metric": {"type": "string", "enum": ["orders", "buyouts", "revenue"],
                               "default": "buyouts"},
                },
                "required": ["product_id"],
            },
        },
    },
    "list_products": {
        "fn": list_products,
        "schema": {
            "name": "list_products",
            "description": "Найти товары компании по имени/offer_id/ozon_sku. Используй чтобы получить product_id перед другими SKU-specific вызовами.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "search": {"type": "string", "description": "Поиск по части названия или артикула. Пусто = все."},
                    "limit": {"type": "integer", "default": 30, "minimum": 1, "maximum": 200},
                },
            },
        },
    },
    "get_pnl_summary": {
        "fn": get_pnl_summary,
        "schema": {
            "name": "get_pnl_summary",
            "description": (
                "Сводный P&L: seller_revenue − все ozon-расходы (комиссии, логистика, "
                "хранение, эквайринг, реклама, return_logistics). БЕЗ COGS и налога."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "default": 30, "minimum": 1, "maximum": 730}
                },
            },
        },
    },
    "get_returns_summary": {
        "fn": get_returns_summary,
        "schema": {
            "name": "get_returns_summary",
            "description": "Сводка возвратов + топ-10 SKU по числу возвратов.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "default": 30, "minimum": 1, "maximum": 730}
                },
            },
        },
    },
}


def tools_schema() -> list[dict]:
    """Список схем tools в формате Anthropic для передачи в Messages API."""
    return [t["schema"] for t in TOOL_REGISTRY.values()]


async def call_tool(
    name: str, args: dict, db: AsyncSession, company_id: uuid.UUID,
) -> dict:
    """Выполнить tool-call. Защита: ловим всё, чтобы LLM-цикл не падал на одном fail."""
    entry = TOOL_REGISTRY.get(name)
    if not entry:
        return {"error": f"Unknown tool: {name}"}
    fn = entry["fn"]
    try:
        return await fn(db, company_id, **(args or {}))
    except TypeError as e:
        return {"error": f"Bad arguments: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"Tool failed: {e}"}
