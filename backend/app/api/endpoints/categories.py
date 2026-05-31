"""
/products/categories — товары по категориям.

- GET /          — плоский список категорий (легаси, для совместимости)
- GET /tree      — дерево категорий Ozon с агрегатами на каждом уровне

Дерево строится из ozon_category_tree (синкается раз в неделю), агрегаты
по выручке/SKU/прибыли — из products + order_items за период.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Order, OrderItem, OzonAccount, OzonCategoryTree, Product, User

router = APIRouter()
UTC = timezone.utc


class CategoryRow(BaseModel):
    category_name: str
    sku_count: int
    revenue: float
    delivered_units: int
    cogs: float
    gross_profit: float
    gross_margin_pct: float | None
    revenue_share_pct: float


class CategoriesResponse(BaseModel):
    period_from: str
    period_to: str
    total_revenue: float
    rows: list[CategoryRow]


@router.get("/", response_model=CategoriesResponse)
async def get_categories(
    days: int = Query(30, ge=1, le=365),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CategoriesResponse:
    period_to = datetime.now(UTC)
    period_from = period_to - timedelta(days=days)

    accs_q = select(OzonAccount.id).where(
        OzonAccount.company_id == current_user.company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if cabinet_ids:
        accs_q = accs_q.where(OzonAccount.id.in_(cabinet_ids))
    accs = [r[0] for r in (await db.execute(accs_q)).all()]
    if not accs:
        return CategoriesResponse(
            period_from=period_from.date().isoformat(),
            period_to=period_to.date().isoformat(),
            total_revenue=0,
            rows=[],
        )

    # SKU count per category
    sku_rows = (await db.execute(
        select(
            func.coalesce(Product.category_name, "(без категории)").label("cat"),
            func.count(Product.id).label("sku_count"),
        )
        .where(Product.ozon_account_id.in_(accs), Product.deleted_at.is_(None))
        .group_by("cat")
    )).all()
    sku_map = {r.cat: int(r.sku_count) for r in sku_rows}

    # Revenue + cogs + delivered_units per category
    rev_rows = (await db.execute(
        select(
            func.coalesce(Product.category_name, "(без категории)").label("cat"),
            func.coalesce(func.sum(OrderItem.total_price), 0).label("revenue"),
            func.coalesce(func.sum(OrderItem.quantity), 0).label("units"),
            func.coalesce(
                func.sum(OrderItem.quantity * func.coalesce(Product.cost_price, 0)), 0
            ).label("cogs"),
        )
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            Order.ozon_account_id.in_(accs),
            Order.order_created_at >= period_from,
            Order.order_created_at < period_to,
            Order.status == "delivered",
        )
        .group_by("cat")
    )).all()

    total_revenue = sum(float(r.revenue or 0) for r in rev_rows)
    rows: list[CategoryRow] = []
    for r in rev_rows:
        rev = float(r.revenue or 0)
        cogs = float(r.cogs or 0)
        gross = rev - cogs
        margin = (gross / rev * 100) if rev > 0 else None
        share = (rev / total_revenue * 100) if total_revenue > 0 else 0
        rows.append(CategoryRow(
            category_name=str(r.cat),
            sku_count=sku_map.get(r.cat, 0),
            revenue=round(rev, 2),
            delivered_units=int(r.units or 0),
            cogs=round(cogs, 2),
            gross_profit=round(gross, 2),
            gross_margin_pct=round(margin, 1) if margin is not None else None,
            revenue_share_pct=round(share, 1),
        ))
    # категории без продаж тоже добавляем
    for cat, n in sku_map.items():
        if not any(r.category_name == cat for r in rows):
            rows.append(CategoryRow(
                category_name=cat, sku_count=n, revenue=0, delivered_units=0,
                cogs=0, gross_profit=0, gross_margin_pct=None, revenue_share_pct=0,
            ))

    rows.sort(key=lambda r: r.revenue, reverse=True)

    return CategoriesResponse(
        period_from=period_from.date().isoformat(),
        period_to=period_to.date().isoformat(),
        total_revenue=round(total_revenue, 2),
        rows=rows,
    )


# ────────────────────────────────────────────────────────────────────
#  /tree — иерархическое дерево с агрегатами на каждом уровне
# ────────────────────────────────────────────────────────────────────

class CategoryTreeNode(BaseModel):
    ozon_id: int
    name: str
    full_path: str
    level: int
    is_type: bool
    is_disabled: bool
    # Агрегаты этого узла + всех потомков
    sku_count: int
    revenue: float
    delivered_units: int
    cogs: float
    gross_profit: float
    gross_margin_pct: float | None
    children: list["CategoryTreeNode"] = []


CategoryTreeNode.model_rebuild()


class CategoryTreeResponse(BaseModel):
    period_from: str
    period_to: str
    total_revenue: float
    nodes_in_db: int           # сколько вообще категорий в дереве (sanity check)
    tree: list[CategoryTreeNode]  # корневые узлы (level=0)
    last_sync: str | None = None


@router.get("/tree", response_model=CategoryTreeResponse)
async def get_categories_tree(
    days: int = Query(30, ge=1, le=365),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    hide_empty: bool = Query(True, description="Скрыть ветки без SKU юзера"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CategoryTreeResponse:
    period_to = datetime.now(UTC)
    period_from = period_to - timedelta(days=days)

    # 1. Все узлы дерева Ozon
    nodes = (await db.execute(
        select(OzonCategoryTree.ozon_id, OzonCategoryTree.name, OzonCategoryTree.parent_id,
               OzonCategoryTree.level, OzonCategoryTree.is_type, OzonCategoryTree.is_disabled,
               OzonCategoryTree.full_path)
    )).all()

    if not nodes:
        return CategoryTreeResponse(
            period_from=period_from.date().isoformat(),
            period_to=period_to.date().isoformat(),
            total_revenue=0, nodes_in_db=0, tree=[],
        )

    # 2. Кабинеты юзера
    accs_q = select(OzonAccount.id).where(
        OzonAccount.company_id == current_user.company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if cabinet_ids:
        accs_q = accs_q.where(OzonAccount.id.in_(cabinet_ids))
    accs = [r[0] for r in (await db.execute(accs_q)).all()]

    # 3. Агрегаты по products.category_id (это leaf = type_id из дерева)
    leaf_agg: dict[int, dict] = {}
    if accs:
        # SKU count per type
        sku_rows = (await db.execute(
            select(Product.category_id, func.count(Product.id))
            .where(Product.ozon_account_id.in_(accs), Product.deleted_at.is_(None),
                   Product.category_id.isnot(None))
            .group_by(Product.category_id)
        )).all()
        for cid, n in sku_rows:
            leaf_agg.setdefault(int(cid), {"sku": 0, "rev": 0.0, "units": 0, "cogs": 0.0})
            leaf_agg[int(cid)]["sku"] = int(n)

        # Revenue / units / cogs per type за период
        rev_rows = (await db.execute(
            select(
                Product.category_id,
                func.coalesce(func.sum(OrderItem.total_price), 0),
                func.coalesce(func.sum(OrderItem.quantity), 0),
                func.coalesce(
                    func.sum(OrderItem.quantity * func.coalesce(Product.cost_price, 0)), 0
                ),
            )
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id)
            .where(
                Order.ozon_account_id.in_(accs),
                Order.order_created_at >= period_from,
                Order.order_created_at < period_to,
                Order.status == "delivered",
                Product.category_id.isnot(None),
            )
            .group_by(Product.category_id)
        )).all()
        for cid, rev, units, cogs in rev_rows:
            leaf_agg.setdefault(int(cid), {"sku": 0, "rev": 0.0, "units": 0, "cogs": 0.0})
            leaf_agg[int(cid)]["rev"] = float(rev)
            leaf_agg[int(cid)]["units"] = int(units)
            leaf_agg[int(cid)]["cogs"] = float(cogs)

    # 4. Строим дерево + агрегируем снизу вверх
    by_id: dict[int, dict] = {}
    for row in nodes:
        by_id[row.ozon_id] = {
            "ozon_id": row.ozon_id, "name": row.name, "parent_id": row.parent_id,
            "level": row.level, "is_type": row.is_type, "is_disabled": row.is_disabled,
            "full_path": row.full_path, "children_ids": [],
            "sku": 0, "rev": 0.0, "units": 0, "cogs": 0.0,
        }
    for n in by_id.values():
        if n["parent_id"] and n["parent_id"] in by_id:
            by_id[n["parent_id"]]["children_ids"].append(n["ozon_id"])

    # Подставляем агрегаты в листья
    for cid, agg in leaf_agg.items():
        if cid in by_id:
            by_id[cid].update({"sku": agg["sku"], "rev": agg["rev"],
                               "units": agg["units"], "cogs": agg["cogs"]})

    # Поднимаем агрегаты от листьев к корню — обходим по убыванию level
    nodes_by_level = sorted(by_id.values(), key=lambda x: -x["level"])
    for n in nodes_by_level:
        if n["parent_id"] and n["parent_id"] in by_id:
            p = by_id[n["parent_id"]]
            p["sku"] += n["sku"]; p["rev"] += n["rev"]
            p["units"] += n["units"]; p["cogs"] += n["cogs"]

    total_rev = sum(n["rev"] for n in by_id.values() if n["level"] == 0)

    def to_tree_node(n: dict) -> CategoryTreeNode | None:
        if hide_empty and n["sku"] == 0:
            return None
        gross = n["rev"] - n["cogs"]
        margin = (gross / n["rev"] * 100) if n["rev"] > 0 else None
        children: list[CategoryTreeNode] = []
        for cid in n["children_ids"]:
            ch = to_tree_node(by_id[cid])
            if ch:
                children.append(ch)
        children.sort(key=lambda c: c.revenue, reverse=True)
        return CategoryTreeNode(
            ozon_id=n["ozon_id"], name=n["name"], full_path=n["full_path"],
            level=n["level"], is_type=n["is_type"], is_disabled=n["is_disabled"],
            sku_count=n["sku"], revenue=round(n["rev"], 2),
            delivered_units=n["units"], cogs=round(n["cogs"], 2),
            gross_profit=round(gross, 2),
            gross_margin_pct=round(margin, 1) if margin is not None else None,
            children=children,
        )

    roots: list[CategoryTreeNode] = []
    for n in by_id.values():
        if n["level"] == 0:
            tn = to_tree_node(n)
            if tn:
                roots.append(tn)
    roots.sort(key=lambda c: c.revenue, reverse=True)

    return CategoryTreeResponse(
        period_from=period_from.date().isoformat(),
        period_to=period_to.date().isoformat(),
        total_revenue=round(total_rev, 2),
        nodes_in_db=len(by_id),
        tree=roots,
    )
