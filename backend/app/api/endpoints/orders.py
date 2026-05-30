"""
Orders API — таблица заказов с серверной пагинацией и фильтрами.

GET /api/v1/orders
  ?page=1&page_size=50
  &cabinet_ids=<uuid>&cabinet_ids=<uuid>
  &date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
  &status=delivered|cancelled|...
  &search=<posting_number или offer_id>

Сортировка: всегда order_created_at DESC (новые сверху).
"""
from __future__ import annotations

import uuid
from datetime import datetime, date as date_cls, timedelta, timezone

UTC = timezone.utc

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Order, OrderItem, OzonAccount, User

router = APIRouter()


class OrderItemRow(BaseModel):
    product_id: str | None
    offer_id: str | None
    name: str | None
    quantity: int
    price: float
    total_price: float


class OrderRow(BaseModel):
    id: str
    posting_number: str
    order_number: str | None
    order_type: str            # fbo / fbs
    status: str
    cabinet_id: str
    cabinet_name: str
    total_amount: float
    commission_amount: float
    delivery_price: float
    cluster_to: str | None
    order_created_at: str | None
    delivered_at: str | None
    items: list[OrderItemRow]


class OrdersListResponse(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[OrderRow]


@router.get("/", response_model=OrdersListResponse)
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    status: str | None = Query(None),
    order_type: str | None = Query(None, description="fbo | fbs"),
    search: str | None = Query(None, description="ищем по posting_number / order_number / offer_id"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrdersListResponse:
    # Кабинеты компании юзера, отфильтрованные по cabinet_ids
    accounts_q = select(OzonAccount.id, OzonAccount.name).where(
        OzonAccount.company_id == current_user.company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if cabinet_ids:
        accounts_q = accounts_q.where(OzonAccount.id.in_(cabinet_ids))
    accounts_rows = (await db.execute(accounts_q)).all()
    account_ids = [r[0] for r in accounts_rows]
    cabinet_names = {str(r[0]): r[1] for r in accounts_rows}

    if not account_ids:
        return OrdersListResponse(page=page, page_size=page_size, total=0, items=[])

    # Базовые WHERE
    where_clauses = [Order.ozon_account_id.in_(account_ids)]
    if date_from:
        where_clauses.append(Order.order_created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        # date_to включительно — берём весь день
        where_clauses.append(Order.order_created_at < datetime.combine(date_to, datetime.max.time()))
    if status:
        where_clauses.append(Order.status == status)
    if order_type:
        # Ozon шлёт строкой "fbo"/"fbs" в нижнем регистре
        where_clauses.append(Order.order_type == order_type.lower())

    # Поиск: posting_number ILIKE OR order_number ILIKE OR EXISTS(item.offer_id ILIKE)
    if search:
        s = f"%{search.strip()}%"
        # subquery для поиска по offer_id внутри items
        match_offer_subq = (
            select(OrderItem.order_id)
            .where(OrderItem.offer_id.ilike(s))
            .scalar_subquery()
        )
        where_clauses.append(
            or_(
                Order.posting_number.ilike(s),
                Order.order_number.ilike(s),
                Order.id.in_(match_offer_subq),
            )
        )

    # Total count
    total_q = select(func.count()).select_from(Order).where(*where_clauses)
    total = int((await db.execute(total_q)).scalar() or 0)

    # Page rows
    offset = (page - 1) * page_size
    rows_q = (
        select(Order)
        .where(*where_clauses)
        .order_by(desc(Order.order_created_at))
        .offset(offset)
        .limit(page_size)
    )
    orders = list((await db.execute(rows_q)).scalars().all())

    # Pre-fetch items для этой страницы одним запросом
    order_ids = [o.id for o in orders]
    items_by_order: dict[uuid.UUID, list[OrderItemRow]] = {}
    if order_ids:
        items_rows = (
            await db.execute(
                select(OrderItem).where(OrderItem.order_id.in_(order_ids))
            )
        ).scalars().all()
        for item in items_rows:
            items_by_order.setdefault(item.order_id, []).append(
                OrderItemRow(
                    product_id=str(item.product_id) if item.product_id else None,
                    offer_id=item.offer_id,
                    name=item.name,
                    quantity=item.quantity,
                    price=float(item.price or 0),
                    total_price=float(item.total_price or 0),
                )
            )

    items: list[OrderRow] = []
    for o in orders:
        items.append(
            OrderRow(
                id=str(o.id),
                posting_number=o.posting_number,
                order_number=o.order_number,
                order_type=o.order_type,
                status=o.status,
                cabinet_id=str(o.ozon_account_id),
                cabinet_name=cabinet_names.get(str(o.ozon_account_id), ""),
                total_amount=float(o.total_amount or 0),
                commission_amount=float(o.commission_amount or 0),
                delivery_price=float(o.delivery_price or 0),
                cluster_to=o.cluster_to,
                order_created_at=o.order_created_at.isoformat() if o.order_created_at else None,
                delivered_at=o.delivered_at.isoformat() if o.delivered_at else None,
                items=items_by_order.get(o.id, []),
            )
        )

    return OrdersListResponse(
        page=page,
        page_size=page_size,
        total=total,
        items=items,
    )


# =====================================================================
# /orders/daily — график по дням (Ozon-style)
# =====================================================================


class OrdersDailyPoint(BaseModel):
    date: str
    orders: int
    units: int
    revenue: float
    avg_check: float


class OrdersDailyResp(BaseModel):
    period_from: str
    period_to: str
    series: list[OrdersDailyPoint]
    prev_period_series: list[OrdersDailyPoint]
    total_orders: int
    total_units: int
    total_revenue: float
    delta_orders_pct: float | None
    delta_revenue_pct: float | None


@router.get("/daily", response_model=OrdersDailyResp)
async def orders_daily(
    days: int = Query(28, ge=1, le=365),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrdersDailyResp:
    """Дневной ряд заказов — для графика «Заказано»."""
    today = datetime.now(UTC).date()
    date_from = today - timedelta(days=days)
    prev_to = date_from - timedelta(days=1)
    prev_from = prev_to - timedelta(days=days)

    accs_q = select(OzonAccount.id).where(
        OzonAccount.company_id == current_user.company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if cabinet_ids:
        accs_q = accs_q.where(OzonAccount.id.in_(cabinet_ids))
    accs = [r[0] for r in (await db.execute(accs_q)).all()]
    if not accs:
        return OrdersDailyResp(
            period_from=date_from.isoformat(), period_to=today.isoformat(),
            series=[], prev_period_series=[],
            total_orders=0, total_units=0, total_revenue=0,
            delta_orders_pct=None, delta_revenue_pct=None,
        )

    async def _series(d_from, d_to) -> list[OrdersDailyPoint]:
        rows = (await db.execute(
            select(
                func.date_trunc("day", Order.created_at).label("d"),
                func.count(func.distinct(Order.id)).label("orders"),
                func.coalesce(func.sum(OrderItem.quantity), 0).label("units"),
                func.coalesce(func.sum(OrderItem.total_price), 0).label("revenue"),
            )
            .select_from(Order)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .where(
                Order.ozon_account_id.in_(accs),
                Order.created_at >= datetime.combine(d_from, datetime.min.time(), tzinfo=UTC),
                Order.created_at < datetime.combine(d_to + timedelta(days=1), datetime.min.time(), tzinfo=UTC),
            )
            .group_by(func.date_trunc("day", Order.created_at))
            .order_by(func.date_trunc("day", Order.created_at))
        )).all()
        out: list[OrdersDailyPoint] = []
        for d, orders, units, revenue in rows:
            orders_i = int(orders or 0)
            units_i = int(units or 0)
            rev_f = float(revenue or 0)
            out.append(OrdersDailyPoint(
                date=d.date().isoformat(),
                orders=orders_i, units=units_i,
                revenue=round(rev_f, 2),
                avg_check=round(rev_f / orders_i, 2) if orders_i else 0,
            ))
        return out

    series = await _series(date_from, today)
    prev_series = await _series(prev_from, prev_to)

    total_orders = sum(p.orders for p in series)
    total_units = sum(p.units for p in series)
    total_revenue = round(sum(p.revenue for p in series), 2)
    prev_orders = sum(p.orders for p in prev_series)
    prev_revenue = sum(p.revenue for p in prev_series)
    delta_orders = ((total_orders - prev_orders) / prev_orders * 100) if prev_orders else None
    delta_revenue = ((total_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue else None

    return OrdersDailyResp(
        period_from=date_from.isoformat(),
        period_to=today.isoformat(),
        series=series,
        prev_period_series=prev_series,
        total_orders=total_orders,
        total_units=total_units,
        total_revenue=total_revenue,
        delta_orders_pct=round(delta_orders, 1) if delta_orders is not None else None,
        delta_revenue_pct=round(delta_revenue, 1) if delta_revenue is not None else None,
    )
