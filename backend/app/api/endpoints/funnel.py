"""
Воронка конверсии — analytics_daily.

GET /api/v1/analytics/funnel?days=30&cabinet_ids=...&compare=true

Шаги воронки:
  1. Показы = hits_view (общая метрика Ozon UI; fallback search+pdp до ре-синка)
  2. В корзину = hits_tocart_search + hits_tocart_pdp
  3. Заказы = ordered_units
  4. Доставлено = delivered_units

Конверсии:
  Корзина % = в_корзину / показы
  Заказ % = заказы / в_корзину
  Выкуп % = доставлено / заказы
  Сквозная % = доставлено / показы

GET /api/v1/analytics/funnel/products?days=30&sort=conversion_desc — топ-10
товаров с разбивкой по той же воронке.
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import AnalyticsDaily, OzonAccount, Product, User

router = APIRouter()


class FunnelStep(BaseModel):
    label: str
    value: int
    pct_from_previous: float | None   # конверсия от предыдущего шага
    pct_from_first: float | None       # доля от показов


class FunnelKPI(BaseModel):
    impressions: int
    to_cart: int
    orders: int
    delivered: int

    cart_conv_pct: float | None         # в_корзину / показы × 100
    order_conv_pct: float | None        # заказы / в_корзину × 100
    delivery_conv_pct: float | None     # доставлено / заказы × 100
    overall_conv_pct: float | None      # доставлено / показы × 100


class FunnelResponse(BaseModel):
    period_from: str
    period_to: str
    cabinet_ids: list[str]
    has_data: bool

    kpi: FunnelKPI
    prev_kpi: FunnelKPI | None
    steps: list[FunnelStep]


class TopProductFunnel(BaseModel):
    product_id: str
    name: str
    offer_id: str
    image_url: str | None

    impressions: int
    to_cart: int
    orders: int
    delivered: int

    cart_conv_pct: float | None
    order_conv_pct: float | None
    delivery_conv_pct: float | None
    overall_conv_pct: float | None


def _safe_pct(num: int | float, denom: int | float) -> float | None:
    if not denom:
        return None
    return round(num / denom * 100, 2)


def _build_kpi(row) -> FunnelKPI:
    imp = int(row.impressions or 0)
    cart = int(row.to_cart or 0)
    orders = int(row.orders or 0)
    deliv = int(row.delivered or 0)
    return FunnelKPI(
        impressions=imp,
        to_cart=cart,
        orders=orders,
        delivered=deliv,
        cart_conv_pct=_safe_pct(cart, imp),
        order_conv_pct=_safe_pct(orders, cart),
        delivery_conv_pct=_safe_pct(deliv, orders),
        overall_conv_pct=_safe_pct(deliv, imp),
    )


async def _account_ids(
    db: AsyncSession, *, company_id: uuid.UUID, cabinet_ids: list[uuid.UUID] | None
) -> list[uuid.UUID]:
    q = select(OzonAccount.id).where(
        OzonAccount.company_id == company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if cabinet_ids:
        q = q.where(OzonAccount.id.in_(cabinet_ids))
    return [r[0] for r in (await db.execute(q)).all()]


async def _funnel_for_window(
    db: AsyncSession,
    *,
    account_ids: list[uuid.UUID],
    date_from: date_cls,
    date_to: date_cls,
):
    """Возвращает Row с алиасами impressions/to_cart/orders/delivered за окно.

    JOIN через Product для фильтра по кабинетам (account_ids).
    """
    return (
        await db.execute(
            select(
                func.coalesce(
                    func.sum(func.coalesce(
                        AnalyticsDaily.hits_view,
                        AnalyticsDaily.hits_view_search + AnalyticsDaily.hits_view_pdp,
                    )), 0
                ).label("impressions"),
                func.coalesce(
                    func.sum(AnalyticsDaily.hits_tocart_search + AnalyticsDaily.hits_tocart_pdp), 0
                ).label("to_cart"),
                func.coalesce(func.sum(AnalyticsDaily.ordered_units), 0).label("orders"),
                func.coalesce(func.sum(AnalyticsDaily.delivered_units), 0).label("delivered"),
            )
            .select_from(AnalyticsDaily)
            .join(Product, Product.id == AnalyticsDaily.product_id)
            .where(
                Product.ozon_account_id.in_(account_ids),
                AnalyticsDaily.date >= date_from,
                AnalyticsDaily.date <= date_to,
            )
        )
    ).one()


@router.get("/", response_model=FunnelResponse)
async def get_funnel(
    days: int = Query(30, ge=1, le=365),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    compare: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FunnelResponse:
    today = datetime.now(UTC := __import__('datetime').timezone.utc).date()
    period_from = today - timedelta(days=days)
    period_to = today

    accs = await _account_ids(db, company_id=current_user.company_id, cabinet_ids=cabinet_ids)
    if not accs:
        empty = FunnelKPI(
            impressions=0, to_cart=0, orders=0, delivered=0,
            cart_conv_pct=None, order_conv_pct=None,
            delivery_conv_pct=None, overall_conv_pct=None,
        )
        return FunnelResponse(
            period_from=period_from.isoformat(),
            period_to=period_to.isoformat(),
            cabinet_ids=[],
            has_data=False,
            kpi=empty, prev_kpi=None, steps=[],
        )

    row = await _funnel_for_window(db, account_ids=accs, date_from=period_from, date_to=period_to)
    kpi = _build_kpi(row)

    prev_kpi: FunnelKPI | None = None
    if compare:
        prev_from = period_from - timedelta(days=days)
        prev_to = period_from - timedelta(days=1)
        prev_row = await _funnel_for_window(
            db, account_ids=accs, date_from=prev_from, date_to=prev_to
        )
        prev_kpi = _build_kpi(prev_row)

    # Шаги для UI визуализации
    steps = [
        FunnelStep(
            label="Показы", value=kpi.impressions,
            pct_from_previous=None,
            pct_from_first=100.0 if kpi.impressions > 0 else None,
        ),
        FunnelStep(
            label="В корзину", value=kpi.to_cart,
            pct_from_previous=kpi.cart_conv_pct,
            pct_from_first=_safe_pct(kpi.to_cart, kpi.impressions),
        ),
        FunnelStep(
            label="Заказы", value=kpi.orders,
            pct_from_previous=kpi.order_conv_pct,
            pct_from_first=_safe_pct(kpi.orders, kpi.impressions),
        ),
        FunnelStep(
            label="Доставлено", value=kpi.delivered,
            pct_from_previous=kpi.delivery_conv_pct,
            pct_from_first=_safe_pct(kpi.delivered, kpi.impressions),
        ),
    ]

    return FunnelResponse(
        period_from=period_from.isoformat(),
        period_to=period_to.isoformat(),
        cabinet_ids=[str(a) for a in accs],
        has_data=kpi.impressions > 0 or kpi.orders > 0,
        kpi=kpi, prev_kpi=prev_kpi, steps=steps,
    )


@router.get("/products", response_model=list[TopProductFunnel])
async def funnel_top_products(
    days: int = Query(30, ge=1, le=365),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    sort: str = Query(
        "delivered_desc",
        description="delivered_desc | impressions_desc | overall_conv_desc | overall_conv_asc",
    ),
    limit: int = Query(20, ge=1, le=100),
    min_impressions: int = Query(
        100, ge=0, description="Фильтр шума: исключаем SKU с малыми показами"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TopProductFunnel]:
    today = datetime.now(__import__('datetime').timezone.utc).date()
    period_from = today - timedelta(days=days)

    accs = await _account_ids(db, company_id=current_user.company_id, cabinet_ids=cabinet_ids)
    if not accs:
        return []

    imp_expr = func.sum(func.coalesce(
        AnalyticsDaily.hits_view,
        AnalyticsDaily.hits_view_search + AnalyticsDaily.hits_view_pdp,
    ))
    cart_expr = func.sum(AnalyticsDaily.hits_tocart_search + AnalyticsDaily.hits_tocart_pdp)
    orders_expr = func.sum(AnalyticsDaily.ordered_units)
    deliv_expr = func.sum(AnalyticsDaily.delivered_units)

    # Постгрес не умеет GROUP BY по json, поэтому НЕ кладём raw_data в SELECT
    # вместе с агрегатами. raw_data достаём отдельным запросом и мерджим.
    rows = (
        await db.execute(
            select(
                Product.id.label("pid"),
                Product.name.label("name"),
                Product.offer_id.label("offer_id"),
                func.coalesce(imp_expr, 0).label("impressions"),
                func.coalesce(cart_expr, 0).label("to_cart"),
                func.coalesce(orders_expr, 0).label("orders"),
                func.coalesce(deliv_expr, 0).label("delivered"),
            )
            .select_from(AnalyticsDaily)
            .join(Product, Product.id == AnalyticsDaily.product_id)
            .where(
                Product.ozon_account_id.in_(accs),
                AnalyticsDaily.date >= period_from,
                AnalyticsDaily.date <= today,
            )
            .group_by(Product.id, Product.name, Product.offer_id)
            .having(func.coalesce(imp_expr, 0) >= min_impressions)
        )
    ).all()

    # raw_data одним запросом по pid'ам
    pids = [r.pid for r in rows]
    image_map: dict[uuid.UUID, str | None] = {}
    if pids:
        img_rows = await db.execute(
            select(Product.id, Product.raw_data).where(Product.id.in_(pids))
        )
        for pid, raw in img_rows.all():
            image_map[pid] = _extract_image(raw)

    result: list[TopProductFunnel] = []
    for r in rows:
        imp = int(r.impressions or 0)
        cart = int(r.to_cart or 0)
        orders = int(r.orders or 0)
        deliv = int(r.delivered or 0)
        result.append(TopProductFunnel(
            product_id=str(r.pid),
            name=r.name,
            offer_id=r.offer_id,
            image_url=image_map.get(r.pid),
            impressions=imp,
            to_cart=cart,
            orders=orders,
            delivered=deliv,
            cart_conv_pct=_safe_pct(cart, imp),
            order_conv_pct=_safe_pct(orders, cart),
            delivery_conv_pct=_safe_pct(deliv, orders),
            overall_conv_pct=_safe_pct(deliv, imp),
        ))

    # сорт
    if sort == "delivered_desc":
        result.sort(key=lambda p: p.delivered, reverse=True)
    elif sort == "impressions_desc":
        result.sort(key=lambda p: p.impressions, reverse=True)
    elif sort == "overall_conv_desc":
        result.sort(key=lambda p: (p.overall_conv_pct or 0), reverse=True)
    elif sort == "overall_conv_asc":
        result.sort(key=lambda p: (p.overall_conv_pct or 999))

    return result[:limit]


@router.get("/products/{product_id}", response_model=TopProductFunnel)
async def funnel_single_product(
    product_id: str,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TopProductFunnel:
    pid = uuid.UUID(product_id)
    today = datetime.now(__import__('datetime').timezone.utc).date()
    period_from = today - timedelta(days=days)

    prod = (await db.execute(
        select(Product).join(OzonAccount, OzonAccount.id == Product.ozon_account_id)
        .where(Product.id == pid, OzonAccount.company_id == current_user.company_id)
    )).scalar_one_or_none()
    if not prod:
        from fastapi import HTTPException
        raise HTTPException(404, "Товар не найден")

    row = (await db.execute(
        select(
            func.coalesce(func.sum(func.coalesce(
                AnalyticsDaily.hits_view,
                AnalyticsDaily.hits_view_search + AnalyticsDaily.hits_view_pdp,
            )), 0).label("imp"),
            func.coalesce(func.sum(AnalyticsDaily.hits_tocart_search + AnalyticsDaily.hits_tocart_pdp), 0).label("cart"),
            func.coalesce(func.sum(AnalyticsDaily.ordered_units), 0).label("orders"),
            func.coalesce(func.sum(AnalyticsDaily.delivered_units), 0).label("deliv"),
        ).where(
            AnalyticsDaily.product_id == pid,
            AnalyticsDaily.date >= period_from,
            AnalyticsDaily.date <= today,
        )
    )).one()

    imp = int(row.imp or 0)
    cart = int(row.cart or 0)
    orders = int(row.orders or 0)
    deliv = int(row.deliv or 0)
    return TopProductFunnel(
        product_id=str(prod.id),
        name=prod.name,
        offer_id=prod.offer_id,
        image_url=_extract_image(prod.raw_data),
        impressions=imp, to_cart=cart, orders=orders, delivered=deliv,
        cart_conv_pct=_safe_pct(cart, imp),
        order_conv_pct=_safe_pct(orders, cart),
        delivery_conv_pct=_safe_pct(deliv, orders),
        overall_conv_pct=_safe_pct(deliv, imp),
    )


def _extract_image(raw: dict | None) -> str | None:
    if not isinstance(raw, dict):
        return None
    primary = raw.get("primary_image")
    if isinstance(primary, list):
        for item in primary:
            if isinstance(item, str) and item:
                return item
    elif isinstance(primary, str) and primary:
        return primary
    return None
