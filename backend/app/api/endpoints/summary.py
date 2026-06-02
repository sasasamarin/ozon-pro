"""
/analytics/summary — сводка KPI по кабинетам в одной таблице.

Каждая строка = один кабинет:
  выручка / заказы / AOV / cogs / Ozon расходы / маржинальная прибыль / маржа %
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
from app.models import Order, OrderItem, OzonAccount, Product, Transaction, User

router = APIRouter()
UTC = timezone.utc

_EXPENSE_FIELDS = (
    "sale_commission", "delivery_to_customer", "return_logistics", "last_mile",
    "storage", "placement", "acquiring", "advertising", "utilization",
)


class CabinetSummaryRow(BaseModel):
    cabinet_id: str
    cabinet_name: str
    premium_tier: str
    sku_count: int
    revenue: float
    orders: int
    aov: float
    cogs: float
    ozon_expenses: float
    marginal_profit: float
    margin_pct: float | None


class SummaryResponse(BaseModel):
    period_from: str
    period_to: str
    rows: list[CabinetSummaryRow]


@router.get("/", response_model=SummaryResponse)
async def get_summary(
    days: int = Query(30, ge=1, le=365),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SummaryResponse:
    if date_from and date_to:
        period_from = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
        period_to = datetime.combine(date_to, datetime.max.time(), tzinfo=UTC)
    else:
        period_to = datetime.now(UTC)
        period_from = period_to - timedelta(days=days)

    accs = (await db.execute(
        select(OzonAccount).where(
            OzonAccount.company_id == current_user.company_id,
            OzonAccount.deleted_at.is_(None),
        )
    )).scalars().all()

    rows: list[CabinetSummaryRow] = []
    for acc in accs:
        # SKU count
        sku_row = await db.execute(
            select(func.count(Product.id)).where(
                Product.ozon_account_id == acc.id, Product.deleted_at.is_(None)
            )
        )
        sku_count = int(sku_row.scalar() or 0)

        # Revenue + orders
        rev_row = (await db.execute(
            select(
                func.coalesce(func.sum(Order.total_amount), 0).label("revenue"),
                func.count(Order.id).label("orders"),
            ).where(
                Order.ozon_account_id == acc.id,
                Order.order_created_at >= period_from,
                Order.order_created_at < period_to,
                Order.status == "delivered",
            )
        )).one()
        revenue = float(rev_row.revenue or 0)
        orders = int(rev_row.orders or 0)

        # COGS
        cogs_row = await db.execute(
            select(
                func.coalesce(
                    func.sum(OrderItem.quantity * func.coalesce(Product.cost_price, 0)), 0
                )
            )
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id)
            .where(
                Order.ozon_account_id == acc.id,
                Order.order_created_at >= period_from,
                Order.order_created_at < period_to,
                Order.status == "delivered",
            )
        )
        cogs = float(cogs_row.scalar() or 0)

        # Ozon expenses
        cols = [
            func.coalesce(func.sum(func.abs(getattr(Transaction, f))), 0).label(f)
            for f in _EXPENSE_FIELDS
        ]
        exp_row = (await db.execute(
            select(*cols).where(
                Transaction.ozon_account_id == acc.id,
                Transaction.time >= period_from,
                Transaction.time < period_to,
            )
        )).one()
        ozon_expenses = sum(float(getattr(exp_row, f) or 0) for f in _EXPENSE_FIELDS)

        marginal_profit = revenue - cogs - ozon_expenses
        aov = revenue / orders if orders > 0 else 0
        margin_pct = (marginal_profit / revenue * 100) if revenue > 0 else None

        rows.append(CabinetSummaryRow(
            cabinet_id=str(acc.id),
            cabinet_name=acc.name,
            premium_tier=acc.premium_tier,
            sku_count=sku_count,
            revenue=round(revenue, 2),
            orders=orders,
            aov=round(aov, 2),
            cogs=round(cogs, 2),
            ozon_expenses=round(ozon_expenses, 2),
            marginal_profit=round(marginal_profit, 2),
            margin_pct=round(margin_pct, 2) if margin_pct is not None else None,
        ))
    rows.sort(key=lambda r: r.revenue, reverse=True)

    return SummaryResponse(
        period_from=period_from.date().isoformat(),
        period_to=period_to.date().isoformat(),
        rows=rows,
    )
