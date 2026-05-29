"""
Параметры поставки товара: lead_time, MOQ, batch_step, safety_stock.

GET  /api/v1/supply-params               — список всех product_supply_params
POST /api/v1/supply-params/{product_id}  — upsert (создать / обновить) для товара
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import OzonAccount, Product, User
from app.models.procurement import ForecastStrategy, ProductSupplyParams

router = APIRouter()
UTC = timezone.utc


class SupplyParamsRow(BaseModel):
    product_id: str
    offer_id: str
    name: str
    cabinet_name: str

    lead_time_total_days: int
    lead_time_production_days: int | None
    lead_time_delivery_days: int | None
    lead_time_processing_days: int | None
    moq: int
    batch_step: int
    batch_strict: bool
    safety_stock_days: int

    longterm_window_days: int
    shortterm_window_days: int
    forecast_strategy: str

    has_record: bool   # есть ли реальная запись в product_supply_params


class SupplyParamsUpdate(BaseModel):
    lead_time_total_days: int = Field(ge=0, le=365)
    lead_time_production_days: int | None = Field(default=None, ge=0, le=365)
    lead_time_delivery_days: int | None = Field(default=None, ge=0, le=365)
    lead_time_processing_days: int | None = Field(default=None, ge=0, le=365)
    moq: int = Field(ge=1)
    batch_step: int = Field(ge=1)
    batch_strict: bool = False
    safety_stock_days: int = Field(ge=0, le=365)
    longterm_window_days: int = Field(default=365, ge=30, le=730)
    shortterm_window_days: int = Field(default=14, ge=3, le=90)
    forecast_strategy: str = Field(default="balanced")


async def _user_id_of_company(db: AsyncSession, *, company_id: uuid.UUID) -> uuid.UUID | None:
    r = await db.execute(
        select(User.id).where(User.company_id == company_id, User.deleted_at.is_(None))
        .order_by(User.created_at).limit(1)
    )
    return r.scalar_one_or_none()


@router.get("/", response_model=list[SupplyParamsRow])
async def list_supply_params(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SupplyParamsRow]:
    """Возвращает все товары компании с их supply-params (или дефолтами)."""
    rows = (await db.execute(
        select(Product, OzonAccount.name.label("cabinet_name"))
        .join(OzonAccount, OzonAccount.id == Product.ozon_account_id)
        .where(
            OzonAccount.company_id == current_user.company_id,
            OzonAccount.deleted_at.is_(None),
            Product.deleted_at.is_(None),
        )
        .order_by(Product.name)
    )).all()

    params_rows = (await db.execute(
        select(ProductSupplyParams).where(
            ProductSupplyParams.product_id.in_([r.Product.id for r in rows])
        )
    )).scalars().all()
    params_map = {p.product_id: p for p in params_rows}

    result: list[SupplyParamsRow] = []
    for row in rows:
        p = row.Product
        sp = params_map.get(p.id)
        result.append(SupplyParamsRow(
            product_id=str(p.id),
            offer_id=p.offer_id,
            name=p.name,
            cabinet_name=row.cabinet_name,
            lead_time_total_days=sp.lead_time_total_days if sp else 14,
            lead_time_production_days=sp.lead_time_production_days if sp else None,
            lead_time_delivery_days=sp.lead_time_delivery_days if sp else None,
            lead_time_processing_days=sp.lead_time_processing_days if sp else None,
            moq=sp.moq if sp else 1,
            batch_step=sp.batch_step if sp else 1,
            batch_strict=sp.batch_strict if sp else False,
            safety_stock_days=sp.safety_stock_days if sp else 7,
            longterm_window_days=sp.longterm_window_days if sp else 365,
            shortterm_window_days=sp.shortterm_window_days if sp else 14,
            forecast_strategy=sp.forecast_strategy if sp else ForecastStrategy.BALANCED.value,
            has_record=sp is not None,
        ))
    return result


@router.post("/{product_id}", response_model=SupplyParamsRow)
async def upsert_supply_params(
    product_id: str,
    payload: SupplyParamsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SupplyParamsRow:
    """UPSERT параметров поставки для одного товара."""
    try:
        pid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(400, "Невалидный product_id")

    prod = (await db.execute(
        select(Product).join(OzonAccount, OzonAccount.id == Product.ozon_account_id)
        .where(Product.id == pid, OzonAccount.company_id == current_user.company_id,
               Product.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not prod:
        raise HTTPException(404, "Товар не найден")

    user_id = await _user_id_of_company(db, company_id=current_user.company_id)
    if not user_id:
        raise HTTPException(500, "У компании нет владельца")

    existing = (await db.execute(
        select(ProductSupplyParams).where(
            ProductSupplyParams.product_id == pid,
            ProductSupplyParams.user_id == user_id,
        )
    )).scalar_one_or_none()

    if existing:
        existing.lead_time_total_days = payload.lead_time_total_days
        existing.lead_time_production_days = payload.lead_time_production_days
        existing.lead_time_delivery_days = payload.lead_time_delivery_days
        existing.lead_time_processing_days = payload.lead_time_processing_days
        existing.moq = payload.moq
        existing.batch_step = payload.batch_step
        existing.batch_strict = payload.batch_strict
        existing.safety_stock_days = payload.safety_stock_days
        existing.longterm_window_days = payload.longterm_window_days
        existing.shortterm_window_days = payload.shortterm_window_days
        existing.forecast_strategy = payload.forecast_strategy
    else:
        existing = ProductSupplyParams(
            user_id=user_id,
            product_id=pid,
            lead_time_total_days=payload.lead_time_total_days,
            lead_time_production_days=payload.lead_time_production_days,
            lead_time_delivery_days=payload.lead_time_delivery_days,
            lead_time_processing_days=payload.lead_time_processing_days,
            moq=payload.moq,
            batch_step=payload.batch_step,
            batch_strict=payload.batch_strict,
            safety_stock_days=payload.safety_stock_days,
            longterm_window_days=payload.longterm_window_days,
            shortterm_window_days=payload.shortterm_window_days,
            forecast_strategy=payload.forecast_strategy,
        )
        db.add(existing)

    await db.commit()
    await db.refresh(existing)

    cabinet_name = (await db.execute(
        select(OzonAccount.name).where(OzonAccount.id == prod.ozon_account_id)
    )).scalar_one()

    return SupplyParamsRow(
        product_id=str(prod.id),
        offer_id=prod.offer_id,
        name=prod.name,
        cabinet_name=cabinet_name,
        lead_time_total_days=existing.lead_time_total_days,
        lead_time_production_days=existing.lead_time_production_days,
        lead_time_delivery_days=existing.lead_time_delivery_days,
        lead_time_processing_days=existing.lead_time_processing_days,
        moq=existing.moq,
        batch_step=existing.batch_step,
        batch_strict=existing.batch_strict,
        safety_stock_days=existing.safety_stock_days,
        longterm_window_days=existing.longterm_window_days,
        shortterm_window_days=existing.shortterm_window_days,
        forecast_strategy=existing.forecast_strategy,
        has_record=True,
    )
