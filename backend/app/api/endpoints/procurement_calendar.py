"""
/api/v1/procurement/calendar — таймлайн поставок по expected_date.

Группирует SupplierOrder-ы по неделям/месяцам с разбивкой по статусам,
показывает просрочки относительно today.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Product, User
from app.models.cost import Supplier, SupplierOrder


router = APIRouter()


class CalendarOrder(BaseModel):
    id: str
    supplier_id: str | None
    supplier_name: str | None
    product_id: str
    product_name: str
    offer_id: str
    qty: int
    total_rub: float
    order_date: str
    expected_date: str | None
    received_date: str | None
    status: str
    overdue_days: int  # 0 если в срок / получен


class CalendarBucket(BaseModel):
    period: str          # 'YYYY-MM-DD' (начало недели) или 'YYYY-MM'
    label: str
    orders_count: int
    total_value_rub: float
    by_status: dict[str, int]
    items: list[CalendarOrder]


class CalendarResp(BaseModel):
    granularity: str
    buckets: list[CalendarBucket]
    summary: dict


def _week_start(d: date) -> date:
    """Понедельник недели."""
    return d - timedelta(days=d.weekday())


@router.get("/calendar", response_model=CalendarResp)
async def procurement_calendar(
    days_back: int = Query(30, ge=0, le=365),
    days_ahead: int = Query(90, ge=7, le=365),
    granularity: str = Query("week", regex="^(week|month)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CalendarResp:
    """Календарь поставок: что приходит когда, что просрочено."""
    today = date.today()
    df = today - timedelta(days=days_back)
    dt = today + timedelta(days=days_ahead)

    # Берём заказы с expected_date в диапазоне ИЛИ без expected (по order_date)
    rows = (await db.execute(
        select(SupplierOrder, Supplier.name, Product.name, Product.offer_id)
        .outerjoin(Supplier, Supplier.id == SupplierOrder.supplier_id)
        .outerjoin(Product, Product.id == SupplierOrder.product_id)
        .where(
            SupplierOrder.user_id == current_user.id,
            SupplierOrder.order_date >= df,
            SupplierOrder.order_date <= dt,
        )
        .order_by(SupplierOrder.expected_date.nullslast(), SupplierOrder.order_date)
    )).all()

    buckets: dict[str, dict] = defaultdict(lambda: {
        "orders": [], "total": 0.0, "count": 0,
        "by_status": defaultdict(int),
    })

    overdue_count = 0
    upcoming_30d_value = 0.0
    total_value = 0.0

    for o, sup_name, prod_name, offer_id in rows:
        anchor = o.expected_date or o.order_date
        if granularity == "week":
            ws = _week_start(anchor)
            key = ws.isoformat()
            label = f"нед. {ws.isoformat()}"
        else:
            key = f"{anchor.year:04d}-{anchor.month:02d}"
            label = key

        total_rub = float(o.unit_price) * o.qty + float(o.delivery_cost)

        # Просрочка: expected_date < today AND не received
        overdue = 0
        if o.expected_date and o.expected_date < today and o.status not in ("received",):
            overdue = (today - o.expected_date).days
            overdue_count += 1

        if o.expected_date and today <= o.expected_date <= today + timedelta(days=30):
            upcoming_30d_value += total_rub

        total_value += total_rub

        co = CalendarOrder(
            id=str(o.id),
            supplier_id=str(o.supplier_id) if o.supplier_id else None,
            supplier_name=sup_name,
            product_id=str(o.product_id),
            product_name=prod_name or "(удалён)",
            offer_id=offer_id or "",
            qty=o.qty,
            total_rub=round(total_rub, 2),
            order_date=o.order_date.isoformat(),
            expected_date=o.expected_date.isoformat() if o.expected_date else None,
            received_date=o.received_date.isoformat() if o.received_date else None,
            status=o.status,
            overdue_days=overdue,
        )
        b = buckets[key]
        b["orders"].append(co)
        b["total"] += total_rub
        b["count"] += 1
        b["by_status"][o.status] += 1

    bucket_list = [
        CalendarBucket(
            period=k,
            label=(f"нед. {k}" if granularity == "week" else k),
            orders_count=v["count"],
            total_value_rub=round(v["total"], 2),
            by_status=dict(v["by_status"]),
            items=v["orders"],
        )
        for k, v in sorted(buckets.items())
    ]

    return CalendarResp(
        granularity=granularity,
        buckets=bucket_list,
        summary={
            "total_orders": len(rows),
            "total_value_rub": round(total_value, 2),
            "overdue_count": overdue_count,
            "upcoming_30d_value_rub": round(upcoming_30d_value, 2),
            "period_from": df.isoformat(),
            "period_to": dt.isoformat(),
        },
    )
