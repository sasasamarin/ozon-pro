"""
Список товаров (все кабинеты текущей компании) + latest stock snapshot.

GET /api/v1/products/ — для страницы /products в UI.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import OzonAccount, Product, Stock, User

router = APIRouter()


def _extract_image_url(raw: dict | None) -> str | None:
    """Из raw_data Ozon /v3/product/info/list достаём URL первой картинки.

    Ozon шлёт primary_image как массив `["url"]`, иногда как строку.
    images — массив строк-URL. Берём первый валидный URL, иначе None.
    """
    if not isinstance(raw, dict):
        return None
    primary = raw.get("primary_image")
    if isinstance(primary, list):
        for item in primary:
            if isinstance(item, str) and item:
                return item
    elif isinstance(primary, str) and primary:
        return primary
    images = raw.get("images") or []
    if isinstance(images, list):
        for item in images:
            if isinstance(item, str) and item:
                return item
            # Иногда images = [{"file_name": "url"}, ...]
            if isinstance(item, dict):
                v = item.get("file_name") or item.get("url")
                if isinstance(v, str) and v:
                    return v
    return None


class ProductStockRow(BaseModel):
    warehouse_type: str
    warehouse_name: str | None
    warehouse_id: int | None
    cluster: str | None
    free_to_sell: int
    reserved: int
    in_transit: int
    snapshot_at: str


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
    rows_all = result.all()
    for row in rows_all:
        product = row.Product
        image_url = _extract_image_url(product.raw_data)
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


@router.get("/{product_id}/stocks", response_model=list[ProductStockRow])
async def product_stocks(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProductStockRow]:
    """Разбивка остатков по складам/типам в последнем snapshot'е.

    Берём время последнего снимка для product_id и возвращаем ВСЕ строки
    stocks этого момента — одна строка на (warehouse_type, warehouse_name).
    """
    import uuid as _uuid

    try:
        pid = _uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Невалидный product_id")

    # Проверяем что товар принадлежит компании юзера
    pcheck = await db.execute(
        select(Product)
        .join(OzonAccount, OzonAccount.id == Product.ozon_account_id)
        .where(
            Product.id == pid,
            OzonAccount.company_id == current_user.company_id,
        )
    )
    if not pcheck.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Товар не найден")

    latest_time_row = await db.execute(
        select(func.max(Stock.time)).where(Stock.product_id == pid)
    )
    latest_time = latest_time_row.scalar_one_or_none()
    if not latest_time:
        return []

    rows = await db.execute(
        select(Stock).where(
            Stock.product_id == pid,
            Stock.time == latest_time,
        ).order_by(Stock.warehouse_type, Stock.warehouse_name)
    )
    return [
        ProductStockRow(
            warehouse_type=s.warehouse_type,
            warehouse_name=s.warehouse_name,
            warehouse_id=s.warehouse_id,
            cluster=s.cluster,
            free_to_sell=s.free_to_sell,
            reserved=s.reserved,
            in_transit=s.in_transit,
            snapshot_at=latest_time.isoformat(),
        )
        for s in rows.scalars().all()
    ]
