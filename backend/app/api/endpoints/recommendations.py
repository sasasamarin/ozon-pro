"""
Recommendations API — точки роста, прогнозы продаж, рекомендация закупки.

GET /api/v1/recommendations/products            — список по всем кабинетам компании
GET /api/v1/recommendations/products/{product_id} — детальная одна карточка
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import OzonAccount, Product, User
from app.services.recommendations import (
    compute_list_recommendations,
    compute_product_recommendation,
)

router = APIRouter()


class _Buyout(BaseModel):
    rate: float
    confidence: str
    sample_size: int
    delivered: int
    returned: int
    arrived_total: int
    basis: str


class _Velocity(BaseModel):
    raw_avg_daily: float
    multiplier: float
    adjusted_daily: float
    confidence: str
    days_in_stock: int
    days_out_of_stock: int
    window_days: int
    total_units_sold: int
    basis: str


class _ROI(BaseModel):
    roi_pct: float
    period_days: int
    profit_rub: float
    capital_rub: float
    confidence: str
    basis: str


class ProductRecommendation(BaseModel):
    product_id: str
    product_name: str
    offer_id: str
    ozon_sku: int
    current_price: float | None
    cost_price: float | None
    image_url: str | None = None
    current_stock: int
    in_transit_to_customer: int

    buyout: _Buyout
    velocity: _Velocity
    procurement: dict[str, Any] | None
    roi_30d: _ROI | None
    abc_class: str | None
    abc_confidence: str | None

    missing_data: list[str]
    worst_cluster: dict[str, Any] | None = None


@router.get("/products", response_model=list[ProductRecommendation])
async def list_recommendations(
    cabinet_ids: list[uuid.UUID] | None = Query(
        None,
        description="Multi-select кабинетов. Если пусто — все кабинеты компании.",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProductRecommendation]:
    """Рекомендации по всем товарам компании с поправкой на фильтр кабинетов."""
    rows = await compute_list_recommendations(
        db,
        company_id=current_user.company_id,
        cabinet_ids=cabinet_ids,
    )
    return [ProductRecommendation(**row) for row in rows]


@router.get("/products/{product_id}", response_model=ProductRecommendation)
async def get_recommendation(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProductRecommendation:
    """Детальная рекомендация по одному товару."""
    try:
        pid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Невалидный product_id")

    # Проверяем что товар принадлежит компании юзера
    result = await db.execute(
        select(Product)
        .join(OzonAccount, OzonAccount.id == Product.ozon_account_id)
        .where(
            Product.id == pid,
            OzonAccount.company_id == current_user.company_id,
            Product.deleted_at.is_(None),
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    rec = await compute_product_recommendation(db, product)
    return ProductRecommendation(**rec)
