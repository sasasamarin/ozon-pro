"""
/products/categories — товары по категориям.

Группировка по products.category_name, агрегат:
  SKU / выручка / делив. / маржа (если есть cost)
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
from app.models import Order, OrderItem, OzonAccount, Product, User

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
