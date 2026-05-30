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

from datetime import date as date_cls, datetime, timedelta, timezone

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import AnalyticsDaily, OzonAccount, Product, Stock, User
from app.services.stock import get_stock

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
    # Total stock считаем через единую логику (см. services/stock.py),
    # но без N+1 — здесь нужна быстрая агрегация. ВАЖНО: дубли AGG+FBO+FBO_WH
    # давали раздутые цифры. Сейчас приоритет: per-warehouse (FBO_WH) или
    # агрегат, но не оба сразу.
    # SQL-вариант: для каждого продукта берём последний снимок отдельно для
    # FBO_WH и для AGG, суммируем согласованно.
    stock_per_product_sql = """
      WITH last_wh AS (
        SELECT product_id, MAX(time) t FROM stocks
        WHERE warehouse_type='FBO_WH' GROUP BY product_id
      ),
      last_agg AS (
        SELECT product_id, MAX(time) t FROM stocks
        WHERE warehouse_type IN ('AGG','FBO','FBS','RFBS') GROUP BY product_id
      ),
      wh_sum AS (
        SELECT s.product_id, COALESCE(SUM(GREATEST(s.free_to_sell - s.reserved, 0)), 0) total
        FROM stocks s JOIN last_wh l ON l.product_id=s.product_id AND l.t=s.time
        WHERE s.warehouse_type='FBO_WH'
        GROUP BY s.product_id
      ),
      agg_sum AS (
        SELECT s.product_id, COALESCE(SUM(GREATEST(s.free_to_sell - s.reserved, 0)), 0) total
        FROM stocks s JOIN last_agg l ON l.product_id=s.product_id AND l.t=s.time
        WHERE s.warehouse_type IN ('FBS','RFBS')
           OR (s.warehouse_type IN ('AGG','FBO')
               AND NOT EXISTS (SELECT 1 FROM last_wh w WHERE w.product_id=s.product_id))
        GROUP BY s.product_id
      )
      SELECT p.id AS p_id,
             COALESCE(wh.total, 0) + COALESCE(ag.total, 0) AS total_stock
      FROM products p
      LEFT JOIN wh_sum  wh ON wh.product_id=p.id
      LEFT JOIN agg_sum ag ON ag.product_id=p.id
    """
    from sqlalchemy import text as _sql_text
    stock_rows = (await db.execute(_sql_text(stock_per_product_sql))).all()
    stock_map: dict[uuid.UUID, int] = {row.p_id: int(row.total_stock or 0) for row in stock_rows}

    query = (
        select(
            Product,
            OzonAccount.id.label("cabinet_id"),
            OzonAccount.name.label("cabinet_name"),
            OzonAccount.premium_tier.label("cabinet_premium_tier"),
        )
        .join(OzonAccount, OzonAccount.id == Product.ozon_account_id)
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
                total_stock=stock_map.get(product.id, 0),
            )
        )

    return items


@router.get("/{product_id}/stock-details")
async def product_stock_details(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Единая разбивка остатков для tooltip/раскрытия — используется ВЕЗДЕ."""
    import uuid as _uuid
    try:
        pid = _uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Невалидный product_id")
    # принадлежность компании
    ok = (await db.execute(
        select(Product.id)
        .join(OzonAccount, OzonAccount.id == Product.ozon_account_id)
        .where(Product.id == pid, OzonAccount.company_id == current_user.company_id)
    )).scalar_one_or_none()
    if not ok:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return (await get_stock(db, pid)).to_dict()


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


# =====================================================================
# КОММИТ 3: Остаток ↔ продажи (для графика «стоимость стокаута»)
# =====================================================================


class StockSalesPoint(BaseModel):
    date: str
    stock: int          # суммарный остаток по всем складам на конец дня
    sales: int          # проданных штук в этот день
    is_stockout: bool   # stock == 0
    revenue: float


class StockoutPeriod(BaseModel):
    start: str
    end: str
    days: int
    lost_units_estimate: int
    lost_revenue_estimate: float


class StockSalesResp(BaseModel):
    product_id: str
    product_name: str | None
    period_from: str
    period_to: str
    history_days_available: int
    earliest_stock_date: str | None
    series: list[StockSalesPoint]
    stockout_periods: list[StockoutPeriod]
    total_stockout_days: int
    total_lost_units: int
    total_lost_revenue: float
    avg_daily_velocity_units: float
    avg_unit_price: float


@router.get("/{product_id}/stock-sales", response_model=StockSalesResp)
async def product_stock_sales(
    product_id: str,
    days: int = Query(90, ge=14, le=730),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StockSalesResp:
    """Остаток + продажи по дням → красные зоны стокаута + цена потерь в рублях."""
    import uuid as _uuid
    UTC = timezone.utc

    try:
        pid = _uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Невалидный product_id")

    # Проверка принадлежности и имя
    pcheck = (await db.execute(
        select(Product)
        .join(OzonAccount, OzonAccount.id == Product.ozon_account_id)
        .where(Product.id == pid, OzonAccount.company_id == current_user.company_id)
    )).scalar_one_or_none()
    if not pcheck:
        raise HTTPException(status_code=404, detail="Товар не найден")

    today = datetime.now(UTC).date()
    date_from = today - timedelta(days=days)

    # === Самая ранняя дата в stocks для этого товара (для «история X дней»)
    earliest_row = (await db.execute(
        select(func.min(Stock.time)).where(Stock.product_id == pid)
    )).scalar_one_or_none()
    earliest_date = earliest_row.date() if earliest_row else None
    if earliest_date:
        history_days_available = (today - earliest_date).days
    else:
        history_days_available = 0

    # === stocks: суммарный остаток на день — берём максимум снапшота за день
    # (если в день было несколько снапшотов — каждый дублирует все склады,
    #  поэтому SUM(free_to_sell) при равных warehouse_id будет неверным;
    #  безопаснее — SUM на максимальный момент дня)
    stocks_rows = (await db.execute(
        select(
            func.date_trunc("day", Stock.time).label("d"),
            func.sum(Stock.free_to_sell).label("stock"),
        )
        .where(
            Stock.product_id == pid,
            Stock.time >= datetime.combine(date_from, datetime.min.time(), tzinfo=UTC),
        )
        .group_by(func.date_trunc("day", Stock.time), Stock.time)
        .order_by(func.date_trunc("day", Stock.time))
    )).all()

    # схлопываем дубликаты по дню — берём минимум остатка (худший момент дня)
    stock_by_day: dict[str, int] = {}
    for r in stocks_rows:
        day = r.d.date().isoformat()
        val = int(r.stock or 0)
        if day in stock_by_day:
            stock_by_day[day] = min(stock_by_day[day], val)
        else:
            stock_by_day[day] = val

    # === продажи по дням
    sales_rows = (await db.execute(
        select(
            AnalyticsDaily.date.label("d"),
            func.coalesce(func.sum(AnalyticsDaily.ordered_units), 0).label("sales"),
            func.coalesce(func.sum(AnalyticsDaily.revenue), 0).label("revenue"),
        )
        .where(
            AnalyticsDaily.product_id == pid,
            AnalyticsDaily.date >= date_from,
        )
        .group_by(AnalyticsDaily.date)
        .order_by(AnalyticsDaily.date)
    )).all()
    sales_by_day = {r.d.isoformat(): (int(r.sales or 0), float(r.revenue or 0)) for r in sales_rows}

    # === собираем единый ряд по диапазону days
    series: list[StockSalesPoint] = []
    last_known_stock = 0
    for i in range(days + 1):
        day = (date_from + timedelta(days=i)).isoformat()
        if day in stock_by_day:
            last_known_stock = stock_by_day[day]
            stock_today = stock_by_day[day]
            has_stock_snapshot = True
        else:
            # forward-fill последнее известное значение
            stock_today = last_known_stock
            has_stock_snapshot = False
        sales, rev = sales_by_day.get(day, (0, 0.0))
        series.append(StockSalesPoint(
            date=day, stock=stock_today, sales=sales,
            is_stockout=(stock_today == 0 and has_stock_snapshot),
            revenue=round(rev, 2),
        ))

    # === velocity и средняя цена (на основе дней когда товар БЫЛ в наличии)
    in_stock_days = [p for p in series if p.stock > 0 and p.sales > 0]
    if in_stock_days:
        total_sales_units = sum(p.sales for p in in_stock_days)
        total_revenue_in_stock = sum(p.revenue for p in in_stock_days)
        avg_velocity = total_sales_units / len(in_stock_days)
        avg_price = total_revenue_in_stock / total_sales_units if total_sales_units else 0
    else:
        avg_velocity = 0
        avg_price = 0

    # === зоны стокаута: непрерывные is_stockout=True
    stockout_periods: list[StockoutPeriod] = []
    cur_start: str | None = None
    cur_days = 0
    for p in series:
        if p.is_stockout:
            if cur_start is None:
                cur_start = p.date
            cur_days += 1
        else:
            if cur_start is not None:
                lost_u = int(round(cur_days * avg_velocity))
                lost_r = round(lost_u * avg_price, 2)
                stockout_periods.append(StockoutPeriod(
                    start=cur_start,
                    end=(date_cls.fromisoformat(p.date) - timedelta(days=1)).isoformat(),
                    days=cur_days, lost_units_estimate=lost_u, lost_revenue_estimate=lost_r,
                ))
                cur_start = None
                cur_days = 0
    if cur_start is not None:
        lost_u = int(round(cur_days * avg_velocity))
        lost_r = round(lost_u * avg_price, 2)
        stockout_periods.append(StockoutPeriod(
            start=cur_start, end=series[-1].date,
            days=cur_days, lost_units_estimate=lost_u, lost_revenue_estimate=lost_r,
        ))

    total_stockout_days = sum(p.days for p in stockout_periods)
    total_lost_units = sum(p.lost_units_estimate for p in stockout_periods)
    total_lost_revenue = round(sum(p.lost_revenue_estimate for p in stockout_periods), 2)

    return StockSalesResp(
        product_id=str(pid),
        product_name=pcheck.name,
        period_from=date_from.isoformat(),
        period_to=today.isoformat(),
        history_days_available=history_days_available,
        earliest_stock_date=earliest_date.isoformat() if earliest_date else None,
        series=series,
        stockout_periods=stockout_periods,
        total_stockout_days=total_stockout_days,
        total_lost_units=total_lost_units,
        total_lost_revenue=total_lost_revenue,
        avg_daily_velocity_units=round(avg_velocity, 2),
        avg_unit_price=round(avg_price, 2),
    )
