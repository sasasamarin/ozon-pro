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
from datetime import datetime, date as date_cls

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
