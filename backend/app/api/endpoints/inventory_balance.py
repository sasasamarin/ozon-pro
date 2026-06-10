"""
«Товарный баланс» — сколько денег ЛЕЖИТ в товаре на складах Ozon.

Per товар:
- current_stock × cost_price   = capital_at_cost (вложено в товар)
- current_stock × selling_price = capital_at_selling (потенциальная выручка)
- разница = potential_margin

+ агрегаты по кабинетам и категориям.

GET /api/v1/inventory/balance?cabinet_ids=...&category_id=...
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.deps_cabinets import get_accessible_cabinet_ids
from app.db.session import get_db
from app.models import User

router = APIRouter()


class BalanceRow(BaseModel):
    product_id: str
    product_name: str
    offer_id: str
    ozon_sku: int
    cabinet_name: str
    category_name: str | None

    current_stock: int
    cost_price: float | None
    selling_price: float | None

    capital_at_cost: float          # current_stock × cost_price
    capital_at_selling: float       # current_stock × selling_price
    potential_margin: float         # capital_at_selling − capital_at_cost
    margin_pct: float | None        # potential_margin / capital_at_selling × 100


class GroupAgg(BaseModel):
    label: str
    units: int
    capital_at_cost: float
    capital_at_selling: float
    potential_margin: float


class BalanceResp(BaseModel):
    rows: list[BalanceRow]
    totals: GroupAgg
    by_cabinet: list[GroupAgg]
    by_category: list[GroupAgg]


@router.get("/balance", response_model=BalanceResp)
async def get_inventory_balance(
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    category_id: int | None = Query(None),
    include_archived: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BalanceResp:
    accessible = await get_accessible_cabinet_ids(db, current_user)
    if accessible is not None and not accessible:
        empty_totals = GroupAgg(
            label="Всего", units=0,
            capital_at_cost=0, capital_at_selling=0, potential_margin=0,
        )
        return BalanceResp(rows=[], totals=empty_totals, by_cabinet=[], by_category=[])

    params: dict = {"cid": str(current_user.company_id)}
    where_cab = ""
    if cabinet_ids:
        where_cab = "AND a.id = ANY(:cab_ids)"
        params["cab_ids"] = [str(x) for x in cabinet_ids]
    where_access = ""
    if accessible is not None:
        where_access = "AND a.id = ANY(:accessible_ids)"
        params["accessible_ids"] = [str(x) for x in accessible]
    where_cat = ""
    if category_id is not None:
        where_cat = "AND p.category_id = :cat"
        params["cat"] = category_id
    where_arch = "" if include_archived else "AND p.is_archived = false"

    # Логика остатков — повторяем /products endpoint: приоритет FBO_WH per-warehouse,
    # иначе AGG/FBO/FBS — без двойного учёта.
    rows = (await db.execute(text(f"""
      WITH last_wh AS (
        SELECT product_id, MAX(time) t FROM stocks
        WHERE warehouse_type='FBO_WH' GROUP BY product_id
      ),
      last_agg AS (
        SELECT product_id, MAX(time) t FROM stocks
        WHERE warehouse_type IN ('AGG','FBO','FBS','RFBS') GROUP BY product_id
      ),
      wh_sum AS (
        SELECT s.product_id,
               COALESCE(SUM(GREATEST(s.free_to_sell - s.reserved, 0)), 0) total
        FROM stocks s JOIN last_wh l ON l.product_id=s.product_id AND l.t=s.time
        WHERE s.warehouse_type='FBO_WH'
        GROUP BY s.product_id
      ),
      agg_sum AS (
        SELECT s.product_id,
               COALESCE(SUM(GREATEST(s.free_to_sell - s.reserved, 0)), 0) total
        FROM stocks s JOIN last_agg l ON l.product_id=s.product_id AND l.t=s.time
        WHERE s.warehouse_type IN ('FBS','RFBS')
           OR (s.warehouse_type IN ('AGG','FBO')
               AND NOT EXISTS (SELECT 1 FROM last_wh w WHERE w.product_id=s.product_id))
        GROUP BY s.product_id
      )
      SELECT p.id::text product_id,
             p.name, p.offer_id, p.ozon_sku,
             a.name AS cabinet_name,
             p.category_name,
             p.cost_price::float    cost_price,
             COALESCE(p.marketing_price, p.current_price)::float selling_price,
             COALESCE(wh.total, 0) + COALESCE(ag.total, 0) AS current_stock
      FROM products p
      JOIN ozon_accounts a ON a.id = p.ozon_account_id
      LEFT JOIN wh_sum wh ON wh.product_id = p.id
      LEFT JOIN agg_sum ag ON ag.product_id = p.id
      WHERE a.company_id = :cid AND a.deleted_at IS NULL AND p.deleted_at IS NULL
        {where_cab} {where_access} {where_cat} {where_arch}
      ORDER BY (COALESCE(wh.total,0) + COALESCE(ag.total,0)) * COALESCE(p.cost_price, 0) DESC
    """), params)).all()

    out: list[BalanceRow] = []
    tot_units = 0
    tot_cost = tot_sell = 0.0
    by_cab_agg: dict[str, GroupAgg] = {}
    by_cat_agg: dict[str, GroupAgg] = {}

    for r in rows:
        stock = int(r.current_stock or 0)
        cost = float(r.cost_price) if r.cost_price else None
        sell = float(r.selling_price) if r.selling_price else None
        cap_cost = (cost or 0) * stock
        cap_sell = (sell or 0) * stock
        margin = cap_sell - cap_cost
        margin_pct = (margin / cap_sell * 100) if cap_sell else None

        out.append(BalanceRow(
            product_id=r.product_id, product_name=r.name,
            offer_id=r.offer_id, ozon_sku=r.ozon_sku,
            cabinet_name=r.cabinet_name, category_name=r.category_name,
            current_stock=stock,
            cost_price=cost, selling_price=sell,
            capital_at_cost=round(cap_cost, 2),
            capital_at_selling=round(cap_sell, 2),
            potential_margin=round(margin, 2),
            margin_pct=round(margin_pct, 2) if margin_pct is not None else None,
        ))

        tot_units += stock
        tot_cost += cap_cost
        tot_sell += cap_sell

        for grp_dict, label in [(by_cab_agg, r.cabinet_name), (by_cat_agg, r.category_name or "Без категории")]:
            g = grp_dict.setdefault(label, GroupAgg(
                label=label, units=0, capital_at_cost=0, capital_at_selling=0, potential_margin=0,
            ))
            g.units += stock
            g.capital_at_cost += cap_cost
            g.capital_at_selling += cap_sell
            g.potential_margin = g.capital_at_selling - g.capital_at_cost

    # Округление group aggs
    for g in list(by_cab_agg.values()) + list(by_cat_agg.values()):
        g.capital_at_cost = round(g.capital_at_cost, 2)
        g.capital_at_selling = round(g.capital_at_selling, 2)
        g.potential_margin = round(g.potential_margin, 2)

    totals = GroupAgg(
        label="Всего", units=tot_units,
        capital_at_cost=round(tot_cost, 2),
        capital_at_selling=round(tot_sell, 2),
        potential_margin=round(tot_sell - tot_cost, 2),
    )

    return BalanceResp(
        rows=out, totals=totals,
        by_cabinet=sorted(by_cab_agg.values(), key=lambda g: -g.capital_at_cost),
        by_category=sorted(by_cat_agg.values(), key=lambda g: -g.capital_at_cost),
    )
