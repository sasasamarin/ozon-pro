"""
/markers — ручные пометки на товарах + автоматические события (стокауты, изменения цен).

GET    /api/v1/markers          — список с фильтрами (тип, товар, дата)
POST   /api/v1/markers          — создать ручной маркер
DELETE /api/v1/markers/{id}
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Product, User
from app.models.marker import Marker

router = APIRouter()
UTC = timezone.utc


class MarkerRow(BaseModel):
    id: str
    marker_type: str
    title: str
    note: str | None
    product_id: str | None
    product_name: str | None
    offer_id: str | None
    created_at: str


class MarkerCreate(BaseModel):
    marker_type: str
    title: str
    note: str | None = None
    product_id: str | None = None


@router.get("/", response_model=list[MarkerRow])
async def list_markers(
    days: int = Query(90, ge=1, le=730),
    product_id: str | None = Query(None),
    marker_type: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MarkerRow]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    q = select(Marker).where(
        Marker.company_id == current_user.company_id,
        Marker.created_at >= cutoff,
    )
    if product_id:
        try:
            q = q.where(Marker.product_id == uuid.UUID(product_id))
        except ValueError:
            raise HTTPException(400, "Невалидный product_id")
    if marker_type:
        q = q.where(Marker.marker_type == marker_type)
    q = q.order_by(desc(Marker.created_at)).limit(500)
    rows = (await db.execute(q)).scalars().all()

    pids = [r.product_id for r in rows if r.product_id]
    prods: dict[uuid.UUID, Product] = {}
    if pids:
        p_rows = (await db.execute(select(Product).where(Product.id.in_(pids)))).scalars().all()
        prods = {p.id: p for p in p_rows}

    return [
        MarkerRow(
            id=str(m.id),
            marker_type=m.marker_type,
            title=m.title,
            note=m.note,
            product_id=str(m.product_id) if m.product_id else None,
            product_name=prods[m.product_id].name if m.product_id in prods else None,
            offer_id=prods[m.product_id].offer_id if m.product_id in prods else None,
            created_at=m.created_at.isoformat(),
        )
        for m in rows
    ]


@router.post("/", response_model=MarkerRow)
async def create_marker(
    payload: MarkerCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MarkerRow:
    pid: uuid.UUID | None = None
    if payload.product_id:
        try:
            pid = uuid.UUID(payload.product_id)
        except ValueError:
            raise HTTPException(400, "Невалидный product_id")

    m = Marker(
        company_id=current_user.company_id,
        user_id=current_user.id,
        product_id=pid,
        marker_type=payload.marker_type,
        title=payload.title,
        note=payload.note,
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)

    prod = None
    if pid:
        prod = (await db.execute(select(Product).where(Product.id == pid))).scalar_one_or_none()

    return MarkerRow(
        id=str(m.id),
        marker_type=m.marker_type,
        title=m.title,
        note=m.note,
        product_id=str(pid) if pid else None,
        product_name=prod.name if prod else None,
        offer_id=prod.offer_id if prod else None,
        created_at=m.created_at.isoformat(),
    )


@router.delete("/{marker_id}")
async def delete_marker(
    marker_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        mid = uuid.UUID(marker_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")
    m = (await db.execute(
        select(Marker).where(Marker.id == mid, Marker.company_id == current_user.company_id)
    )).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Не найдено")
    await db.delete(m)
    await db.commit()
    return {"deleted": True}
