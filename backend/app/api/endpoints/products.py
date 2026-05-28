"""
Список товаров (все кабинеты текущей компании) + latest stock snapshot.

GET /api/v1/products/ — для страницы /products в UI.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import OzonAccount, Product, Stock, User

router = APIRouter()


class ProductItem(BaseModel):
    id: str
    name: str
    offer_id: str
    ozon_sku: int
    current_price: float | None
    old_price: float | None
    marketing_price: float | None
    min_price: float | None
    price_index: str | None
    is_archived: bool
    image_url: str | None  # пока None — нужен enrichment через /v3/product/info/list
    cabinet_id: str
    cabinet_name: str
    cabinet_premium_tier: str
    total_stock: int  # sum free_to_sell across warehouses в последнем снимке


@router.get("/", response_model=list[ProductItem])
async def list_products(
    cabinet_ids: list[uuid.UUID] | None = Query(
        None, description="Multi-select: повторяющийся параметр (?cabinet_ids=a&cabinet_ids=b). Если пусто — все кабинеты компании."
    ),
    cabinet_id: uuid.UUID | None = Query(
        None, description="Legacy single-select (для обратной совместимости)."
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProductItem]:
    """
    Все товары компании текущего юзера. Подмешиваем latest stock snapshot.

    NB: name + image_url пока заглушки — `/v3/product/list` их не отдаёт.
    Полная информация после интеграции `/v3/product/info/list`.
    """
    # Подзапрос: latest_time для каждого product_id в stocks
    latest_time_subq = (
        select(
            Stock.product_id.label("p_id"),
            func.max(Stock.time).label("latest_time"),
        )
        .group_by(Stock.product_id)
        .subquery()
    )

    # Подзапрос: SUM(free_to_sell) для latest_time каждого товара
    stock_sum_subq = (
        select(
            Stock.product_id.label("p_id"),
            func.coalesce(func.sum(Stock.free_to_sell), 0).label("total_stock"),
        )
        .join(
            latest_time_subq,
            (Stock.product_id == latest_time_subq.c.p_id)
            & (Stock.time == latest_time_subq.c.latest_time),
        )
        .group_by(Stock.product_id)
        .subquery()
    )

    query = (
        select(
            Product,
            OzonAccount.id.label("cabinet_id"),
            OzonAccount.name.label("cabinet_name"),
            OzonAccount.premium_tier.label("cabinet_premium_tier"),
            func.coalesce(stock_sum_subq.c.total_stock, 0).label("total_stock"),
        )
        .join(OzonAccount, OzonAccount.id == Product.ozon_account_id)
        .outerjoin(stock_sum_subq, stock_sum_subq.c.p_id == Product.id)
        .where(
            OzonAccount.company_id == current_user.company_id,
            OzonAccount.deleted_at.is_(None),
            Product.deleted_at.is_(None),
        )
        .order_by(Product.name)
    )

    # Multi-select имеет приоритет; legacy cabinet_id обрабатываем для совместимости
    if cabinet_ids:
        query = query.where(Product.ozon_account_id.in_(cabinet_ids))
    elif cabinet_id:
        query = query.where(Product.ozon_account_id == cabinet_id)

    result = await db.execute(query)
    items: list[ProductItem] = []
    for row in result.all():
        product = row.Product
        raw = product.raw_data or {}
        image_url = (
            raw.get("primary_image")
            or (raw.get("images") or [None])[0]
            if isinstance(raw, dict)
            else None
        )
        items.append(
            ProductItem(
                id=str(product.id),
                name=product.name,
                offer_id=product.offer_id,
                ozon_sku=product.ozon_sku,
                current_price=float(product.current_price) if product.current_price is not None else None,
                old_price=float(product.old_price) if product.old_price is not None else None,
                marketing_price=float(product.marketing_price) if product.marketing_price is not None else None,
                min_price=float(product.min_price) if product.min_price is not None else None,
                price_index=product.price_index,
                is_archived=product.is_archived,
                image_url=image_url,
                cabinet_id=str(row.cabinet_id),
                cabinet_name=row.cabinet_name,
                cabinet_premium_tier=row.cabinet_premium_tier,
                total_stock=int(row.total_stock or 0),
            )
        )

    return items
