"""
Единый источник «текущий остаток per product».

Был дублирован в 5 местах (см. AUDIT.md A1):
  api/endpoints/products.py:116
  api/endpoints/storage_warning.py:103
  api/endpoints/inventory_balance.py:84
  services/analytics_engine.py:130
  services/ai/tools_v2.py:224

Логика: для каждого product_id берём ЛИБО per-warehouse сумму FBO_WH,
ЛИБО aggregate (AGG/FBO/FBS/RFBS), но не оба сразу (иначе дубли —
видели stock=23,427 шт на люстре при реальном 200).

Использование:
    stock_map = await get_current_stock_map(db, company_id=..., cabinet_id=...)
    for p in products:
        p.stock = stock_map.get(p.id, 0)

Перформанс: один SQL на всю компанию (~50-200 SKU) — миллисекунды. N+1
исключён: endpoint делает 2 запроса (stock + main), вместо одного с CTE,
но при <500 SKU это эквивалентно (PostgreSQL оптимизатор всё равно
посчитает stock-агрегат отдельно).
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_current_stock_map(
    db: AsyncSession, *,
    company_id: uuid.UUID | None = None,
    cabinet_id: uuid.UUID | None = None,
    product_ids: list[uuid.UUID] | None = None,
    freshness_days: int = 7,
) -> dict[uuid.UUID, int]:
    """
    Текущий остаток по каждому product_id из последнего снимка (freshness_days).

    Фильтры (любой из):
      company_id — все товары компании
      cabinet_id — товары одного кабинета
      product_ids — конкретные товары

    Возвращает dict[product_id] -> stock (int).
    """
    where_clauses = ["p.is_archived = false"]
    params: dict = {"freshness": timedelta(days=freshness_days)}
    if company_id:
        where_clauses.append("oa.company_id = :cid")
        params["cid"] = str(company_id)
    if cabinet_id:
        where_clauses.append("oa.id = :cab")
        params["cab"] = str(cabinet_id)
    if product_ids:
        where_clauses.append("p.id = ANY(:pids)")
        params["pids"] = [str(p) for p in product_ids]
    where_sql = " AND ".join(where_clauses)

    sql = f"""
        WITH last_wh AS (
            SELECT s.product_id, MAX(s.time) t FROM stocks s
            JOIN products p ON p.id = s.product_id
            JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
            WHERE s.warehouse_type='FBO_WH'
              AND s.time > NOW() - :freshness
              AND {where_sql}
            GROUP BY s.product_id
        ),
        last_agg AS (
            SELECT s.product_id, MAX(s.time) t FROM stocks s
            JOIN products p ON p.id = s.product_id
            JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
            WHERE s.warehouse_type IN ('AGG','FBO','FBS','RFBS')
              AND s.time > NOW() - :freshness
              AND {where_sql}
            GROUP BY s.product_id
        ),
        wh_sum AS (
            SELECT s.product_id,
                   COALESCE(SUM(GREATEST(s.free_to_sell - s.reserved, 0)), 0)::int AS total
            FROM stocks s JOIN last_wh l ON l.product_id=s.product_id AND l.t=s.time
            WHERE s.warehouse_type='FBO_WH'
            GROUP BY s.product_id
        ),
        agg_sum AS (
            SELECT s.product_id,
                   COALESCE(SUM(GREATEST(s.free_to_sell - s.reserved, 0)), 0)::int AS total
            FROM stocks s JOIN last_agg l ON l.product_id=s.product_id AND l.t=s.time
            WHERE s.warehouse_type IN ('FBS','RFBS')
               OR (s.warehouse_type IN ('AGG','FBO')
                   AND NOT EXISTS (SELECT 1 FROM last_wh w WHERE w.product_id=s.product_id))
            GROUP BY s.product_id
        )
        SELECT p.id::text AS pid,
               (COALESCE(wh.total, 0) + COALESCE(ag.total, 0))::int AS stock
        FROM products p
        JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
        LEFT JOIN wh_sum wh ON wh.product_id = p.id
        LEFT JOIN agg_sum ag ON ag.product_id = p.id
        WHERE {where_sql}
    """
    rows = (await db.execute(text(sql), params)).all()
    return {uuid.UUID(r.pid): int(r.stock or 0) for r in rows}


async def get_current_stock(
    db: AsyncSession, product_id: uuid.UUID, freshness_days: int = 7,
) -> int:
    """Удобный wrapper для одного товара."""
    m = await get_current_stock_map(db, product_ids=[product_id], freshness_days=freshness_days)
    return m.get(product_id, 0)
