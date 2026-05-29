"""
/procurement/orders — заказы поставщикам.

GET    /api/v1/procurement/orders     — список с фильтрами (статус, период)
POST   /api/v1/procurement/orders     — создать заказ
PATCH  /api/v1/procurement/orders/{id} — обновить (например, status=received)
DELETE /api/v1/procurement/orders/{id}

При status='received' автоматически создаём ProductCostHistory запись.
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import OzonAccount, Product, User
from app.models.cost import (
    CostConfidence,
    CostSource,
    ProductCostHistory,
    Supplier,
    SupplierOrder,
    SupplierOrderStatus,
)

router = APIRouter()
UTC = timezone.utc


class SupplierOrderRow(BaseModel):
    id: str
    supplier_id: str | None
    supplier_name: str | None
    product_id: str
    product_name: str
    offer_id: str
    qty: int
    unit_price: float
    delivery_cost: float
    total: float
    order_date: str
    expected_date: str | None
    received_date: str | None
    status: str


class SupplierOrderCreate(BaseModel):
    product_id: str
    supplier_id: str | None = None
    qty: int = Field(gt=0)
    unit_price: float = Field(ge=0)
    delivery_cost: float = Field(ge=0, default=0)
    order_date: date_cls
    expected_date: date_cls | None = None
    status: str = SupplierOrderStatus.CREATED.value


class SupplierOrderUpdate(BaseModel):
    qty: int | None = Field(default=None, gt=0)
    unit_price: float | None = Field(default=None, ge=0)
    delivery_cost: float | None = Field(default=None, ge=0)
    expected_date: date_cls | None = None
    received_date: date_cls | None = None
    status: str | None = None


class SupplierRow(BaseModel):
    id: str
    name: str
    contact: str | None
    lead_time_days: int | None


class SupplierCreate(BaseModel):
    name: str
    contact: str | None = None
    lead_time_days: int | None = None
    payment_terms: str | None = None


async def _row(db: AsyncSession, o: SupplierOrder) -> SupplierOrderRow:
    sup = None
    if o.supplier_id:
        sup = (await db.execute(
            select(Supplier).where(Supplier.id == o.supplier_id)
        )).scalar_one_or_none()
    prod = (await db.execute(
        select(Product).where(Product.id == o.product_id)
    )).scalar_one_or_none()
    return SupplierOrderRow(
        id=str(o.id),
        supplier_id=str(o.supplier_id) if o.supplier_id else None,
        supplier_name=sup.name if sup else None,
        product_id=str(o.product_id),
        product_name=prod.name if prod else "(удалён)",
        offer_id=prod.offer_id if prod else "",
        qty=o.qty,
        unit_price=float(o.unit_price),
        delivery_cost=float(o.delivery_cost),
        total=float(o.unit_price) * o.qty + float(o.delivery_cost),
        order_date=o.order_date.isoformat(),
        expected_date=o.expected_date.isoformat() if o.expected_date else None,
        received_date=o.received_date.isoformat() if o.received_date else None,
        status=o.status,
    )


# === Suppliers (CRUD) ===


@router.get("/suppliers", response_model=list[SupplierRow])
async def list_suppliers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SupplierRow]:
    rows = (await db.execute(
        select(Supplier).where(Supplier.user_id == current_user.id)
        .order_by(Supplier.name)
    )).scalars().all()
    return [
        SupplierRow(
            id=str(s.id), name=s.name, contact=s.contact,
            lead_time_days=s.lead_time_days,
        )
        for s in rows
    ]


@router.post("/suppliers", response_model=SupplierRow)
async def create_supplier(
    payload: SupplierCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SupplierRow:
    s = Supplier(
        user_id=current_user.id,
        name=payload.name,
        contact=payload.contact,
        lead_time_days=payload.lead_time_days,
        payment_terms=payload.payment_terms,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return SupplierRow(
        id=str(s.id), name=s.name, contact=s.contact, lead_time_days=s.lead_time_days,
    )


# === Supplier Orders ===


@router.get("/", response_model=list[SupplierOrderRow])
async def list_orders(
    status: str | None = Query(None),
    days: int = Query(365, ge=1, le=1825),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SupplierOrderRow]:
    cutoff = datetime.now(UTC).date() - timedelta(days=days)
    q = select(SupplierOrder).where(
        SupplierOrder.user_id == current_user.id,
        SupplierOrder.order_date >= cutoff,
    )
    if status:
        q = q.where(SupplierOrder.status == status)
    q = q.order_by(desc(SupplierOrder.order_date))
    rows = (await db.execute(q)).scalars().all()
    return [await _row(db, o) for o in rows]


@router.post("/", response_model=SupplierOrderRow)
async def create_order(
    payload: SupplierOrderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SupplierOrderRow:
    try:
        pid = uuid.UUID(payload.product_id)
    except ValueError:
        raise HTTPException(400, "Невалидный product_id")

    prod = (await db.execute(
        select(Product).join(OzonAccount, OzonAccount.id == Product.ozon_account_id)
        .where(Product.id == pid, OzonAccount.company_id == current_user.company_id)
    )).scalar_one_or_none()
    if not prod:
        raise HTTPException(404, "Товар не найден")

    sup_id = None
    if payload.supplier_id:
        try:
            sup_id = uuid.UUID(payload.supplier_id)
        except ValueError:
            raise HTTPException(400, "Невалидный supplier_id")

    o = SupplierOrder(
        user_id=current_user.id,
        ozon_account_id=prod.ozon_account_id,
        supplier_id=sup_id,
        product_id=pid,
        qty=payload.qty,
        unit_price=payload.unit_price,
        delivery_cost=payload.delivery_cost,
        order_date=payload.order_date,
        expected_date=payload.expected_date,
        status=payload.status,
    )
    db.add(o)
    await db.commit()
    await db.refresh(o)
    return await _row(db, o)


@router.patch("/{order_id}", response_model=SupplierOrderRow)
async def update_order(
    order_id: str,
    payload: SupplierOrderUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SupplierOrderRow:
    try:
        oid = uuid.UUID(order_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")

    o = (await db.execute(
        select(SupplierOrder).where(
            SupplierOrder.id == oid, SupplierOrder.user_id == current_user.id
        )
    )).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "Не найдено")

    if payload.qty is not None:
        o.qty = payload.qty
    if payload.unit_price is not None:
        o.unit_price = payload.unit_price
    if payload.delivery_cost is not None:
        o.delivery_cost = payload.delivery_cost
    if payload.expected_date is not None:
        o.expected_date = payload.expected_date
    if payload.received_date is not None:
        o.received_date = payload.received_date
    if payload.status is not None:
        o.status = payload.status
        # При status=received создаём ProductCostHistory
        if payload.status == SupplierOrderStatus.RECEIVED.value and o.received_date is None:
            o.received_date = datetime.now(UTC).date()

        if payload.status == SupplierOrderStatus.RECEIVED.value:
            now = datetime.now(UTC)
            full_cost = float(o.unit_price) + (float(o.delivery_cost) / o.qty)
            # Закрываем предыдущую запись
            existing = (await db.execute(
                select(ProductCostHistory).where(
                    ProductCostHistory.product_id == o.product_id,
                    ProductCostHistory.effective_to.is_(None),
                )
            )).scalars().all()
            for e in existing:
                e.effective_to = now
            db.add(ProductCostHistory(
                effective_from=now,
                product_id=o.product_id,
                ozon_account_id=o.ozon_account_id,
                user_id=current_user.id,
                purchase_price=o.unit_price,
                delivery_to_wh=float(o.delivery_cost) / o.qty,
                packaging=0,
                other_costs=0,
                full_cost=full_cost,
                source=CostSource.SUPPLIER_ORDER.value,
                confidence=CostConfidence.EXACT.value,
                created_by_user_id=current_user.id,
            ))
            # Денормализованный апдейт products.cost_price
            prod = (await db.execute(
                select(Product).where(Product.id == o.product_id)
            )).scalar_one_or_none()
            if prod:
                prod.cost_price = full_cost
    await db.commit()
    await db.refresh(o)
    return await _row(db, o)


@router.delete("/{order_id}")
async def delete_order(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        oid = uuid.UUID(order_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")
    o = (await db.execute(
        select(SupplierOrder).where(
            SupplierOrder.id == oid, SupplierOrder.user_id == current_user.id
        )
    )).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "Не найдено")
    await db.delete(o)
    await db.commit()
    return {"deleted": True}
