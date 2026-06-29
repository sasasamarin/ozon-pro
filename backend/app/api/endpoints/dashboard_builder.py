"""
/dashboard/builder — конструктор графиков (custom graph cards).

Endpoints:
- GET  /layout              — раскладка текущего пользователя (cards + scope)
- PUT  /layout              — сохранить раскладку (full replace cards JSONB)
- GET  /series              — данные временного ряда по cabinet_ids + metric_keys
- GET  /metrics             — переиспользуется реестр из product_stats

Series-endpoint считает метрики ПО СПИСКУ КАБИНЕТОВ (вся продукция, не один SKU).
Логика свёртки (day/week/month) переиспользует aggregate_bucket из product_metrics.
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.deps_cabinets import get_accessible_cabinet_ids
from app.db.session import get_db
from app.models import DashboardLayout, OzonAccount, User
from app.services.product_metrics import METRICS_BY_KEY, aggregate_bucket

router = APIRouter()
UTC = timezone.utc


class LayoutResp(BaseModel):
    id: str
    scope: str
    name: str | None
    cards: list[dict[str, Any]]


class LayoutIn(BaseModel):
    scope: str = "cabinet"
    name: str | None = None
    cards: list[dict[str, Any]]


class SeriesPoint(BaseModel):
    date: str
    values: dict[str, float | None]


class SeriesResponse(BaseModel):
    interval: str
    points: list[SeriesPoint]


# ============================================================
# Layout CRUD (один документ per (user, scope))
# ============================================================


@router.get("/layout", response_model=LayoutResp)
async def get_layout(
    scope: str = "cabinet",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LayoutResp:
    layout = (await db.execute(
        select(DashboardLayout).where(
            DashboardLayout.user_id == current_user.id,
            DashboardLayout.scope == scope,
        )
    )).scalar_one_or_none()
    if not layout:
        # Создаём пустую раскладку on-demand
        layout = DashboardLayout(
            user_id=current_user.id, company_id=current_user.company_id,
            scope=scope, cards=[],
        )
        db.add(layout)
        await db.commit()
        await db.refresh(layout)
    return LayoutResp(
        id=str(layout.id), scope=layout.scope, name=layout.name,
        cards=layout.cards or [],
    )


@router.put("/layout", response_model=LayoutResp)
async def save_layout(
    payload: LayoutIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LayoutResp:
    # upsert
    stmt = pg_insert(DashboardLayout).values(
        user_id=current_user.id, company_id=current_user.company_id,
        scope=payload.scope, name=payload.name, cards=payload.cards,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_layout_user_scope",
        set_={"cards": stmt.excluded.cards, "name": stmt.excluded.name,
              "updated_at": datetime.now(UTC)},
    )
    await db.execute(stmt)
    await db.commit()
    layout = (await db.execute(
        select(DashboardLayout).where(
            DashboardLayout.user_id == current_user.id,
            DashboardLayout.scope == payload.scope,
        )
    )).scalar_one()
    return LayoutResp(
        id=str(layout.id), scope=layout.scope, name=layout.name,
        cards=layout.cards or [],
    )


# ============================================================
# Series — данные для графика по списку кабинетов
# ============================================================


async def _fetch_daily_cabinet(
    db: AsyncSession,
    cabinet_ids: list[uuid.UUID],
    date_from: date_cls,
    date_to: date_cls,
) -> dict[date_cls, dict[str, float | None]]:
    """Собирает дневные метрики по списку кабинетов (вся продукция).

    Использует тот же набор таблиц что product_stats (analytics_daily,
    ad_statistics, orders+items, returns, stocks), но БЕЗ фильтра по product_id.
    """
    rows: dict[date_cls, dict[str, float | None]] = {}

    def _ensure(d: date_cls) -> dict:
        if d not in rows:
            rows[d] = {}
        return rows[d]

    params = {"cabs": [str(c) for c in cabinet_ids], "df": date_from, "dt": date_to}

    # analytics_daily через products (там нет cabinet_id напрямую)
    ad_rows = (await db.execute(text("""
        SELECT ad.date,
               SUM(COALESCE(hits_view_search, 0))::float AS impressions,
               SUM(COALESCE(hits_view_pdp, 0))::float AS clicks,
               SUM(COALESCE(hits_tocart_search,0)+COALESCE(hits_tocart_pdp,0))::float AS cart_count,
               AVG(COALESCE(position_category,0)::float) AS position_search
        FROM analytics_daily ad
        JOIN products p ON p.id = ad.product_id
        WHERE p.ozon_account_id = ANY(:cabs)
          AND ad.date >= :df AND ad.date <= :dt
        GROUP BY ad.date
    """), params)).all()
    for r in ad_rows:
        d = _ensure(r.date)
        d["impressions"] = float(r.impressions or 0)
        d["clicks"] = float(r.clicks or 0)
        d["cart_count"] = float(r.cart_count or 0)
        d["position_search"] = float(r.position_search or 0) or None

    # ad_statistics
    ad_stat = (await db.execute(text("""
        SELECT date,
               SUM(impressions)::float AS imp,
               SUM(clicks)::float AS clicks,
               SUM(orders)::float AS orders,
               SUM(spend)::float AS spend,
               SUM(revenue)::float AS rev
        FROM ad_statistics
        WHERE ozon_account_id = ANY(:cabs)
          AND date >= :df AND date <= :dt
        GROUP BY date
    """), params)).all()
    for r in ad_stat:
        d = _ensure(r.date)
        d["ad_impressions"] = float(r.imp or 0)
        d["ad_clicks"] = float(r.clicks or 0)
        d["ad_orders"] = float(r.orders or 0)
        d["ad_spend"] = float(r.spend or 0)

    # orders + order_items — главный источник заказов/выручки
    orders_rows = (await db.execute(text("""
        SELECT DATE(o.order_created_at) AS d,
               SUM(oi.quantity)::float AS orders_qty,
               SUM(oi.quantity) FILTER (WHERE o.status = 'delivered')::float AS delivered_qty,
               SUM(oi.quantity) FILTER (WHERE o.status = 'cancelled')::float AS cancelled_qty,
               SUM(oi.price * oi.quantity)::float AS revenue,
               AVG(oi.price)::float AS seller_price,
               SUM(oi.customer_price * oi.quantity)::float / NULLIF(SUM(oi.quantity), 0) AS customer_price
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE o.ozon_account_id = ANY(:cabs)
          AND o.order_created_at >= :df
          AND o.order_created_at < (CAST(:dt AS date) + INTERVAL '1 day')
        GROUP BY 1
    """), params)).all()
    for r in orders_rows:
        d = _ensure(r.d)
        d["orders"] = float(r.orders_qty or 0)
        d["delivered"] = float(r.delivered_qty or 0)
        d["cancelled"] = float(r.cancelled_qty or 0)
        d["revenue"] = float(r.revenue or 0)
        d["seller_price"] = float(r.seller_price or 0) or None
        d["customer_price"] = float(r.customer_price or 0) or None

    # seller_revenue — accruals_for_sale из transactions (что Ozon реально
    # начислил продавцу, включая Баллы за скидки и Программы партнёров).
    # Источник истины P&L. По operation_date — это дата ДОСТАВКИ, не заказа.
    sr_rows = (await db.execute(text("""
        SELECT operation_date::date AS d,
               COALESCE(SUM(accruals_for_sale), 0)::float AS sr
        FROM transactions
        WHERE ozon_account_id = ANY(:cabs)
          AND operation_type = 'OperationAgentDeliveredToCustomer'
          AND operation_date >= :df
          AND operation_date <= :dt
        GROUP BY 1
    """), params)).all()
    for r in sr_rows:
        _ensure(r.d)["seller_revenue"] = float(r.sr or 0)

    # returns
    ret = (await db.execute(text("""
        SELECT DATE(return_date) d, SUM(quantity)::float qty
        FROM returns
        WHERE ozon_account_id = ANY(:cabs)
          AND return_date >= :df AND return_date <= :dt
        GROUP BY 1
    """), params)).all()
    for r in ret:
        _ensure(r.d)["returned_after"] = float(r.qty or 0)

    # stocks
    st = (await db.execute(text("""
        SELECT DATE(s.time) d,
               SUM(s.free_to_sell)::float AS free,
               SUM(s.in_transit)::float AS in_t
        FROM stocks s
        JOIN products p ON p.id = s.product_id
        WHERE p.ozon_account_id = ANY(:cabs)
          AND s.time >= :df AND s.time < (CAST(:dt AS date) + INTERVAL '1 day')
        GROUP BY 1
    """), params)).all()
    for r in st:
        d = _ensure(r.d)
        d["stock_warehouse"] = float(r.free or 0)
        d["in_transit_to"] = float(r.in_t or 0)

    # Derived
    for m in rows.values():
        imp = m.get("impressions") or 0
        ad_imp = m.get("ad_impressions") or 0
        clicks = m.get("clicks") or 0
        ad_clicks = m.get("ad_clicks") or 0
        orders_v = m.get("orders") or 0
        cart = m.get("cart_count") or 0
        delivered = m.get("delivered") or 0
        ad_spend = m.get("ad_spend") or 0
        ad_orders = m.get("ad_orders") or 0
        revenue = m.get("revenue") or 0
        seller = m.get("seller_price")
        customer = m.get("customer_price")
        stock_w = m.get("stock_warehouse") or 0
        in_t = m.get("in_transit_to") or 0

        m["ad_imp_share"] = (ad_imp / imp * 100) if imp > 0 else None
        m["organic_clicks"] = clicks - ad_clicks if clicks else None
        m["ctr"] = (clicks / imp * 100) if imp > 0 else None
        m["ad_traffic_share"] = (ad_clicks / clicks * 100) if clicks > 0 else None
        m["conv_click_to_cart"] = (cart / clicks * 100) if clicks > 0 else None
        m["conv_cart_to_order"] = (orders_v / cart * 100) if cart > 0 else None
        m["conv_click_to_order"] = (orders_v / clicks * 100) if clicks > 0 else None
        m["buyout_rate"] = (delivered / orders_v * 100) if orders_v > 0 else None
        m["cpo"] = (ad_spend / ad_orders) if ad_orders > 0 else None
        m["cps"] = (ad_spend / orders_v) if orders_v > 0 else None
        m["drr"] = (ad_spend / revenue * 100) if revenue > 0 else None
        if seller and customer:
            m["spp_pct"] = (seller - customer) / seller * 100
        m["stock_total"] = stock_w + in_t

    return rows


def _bucket_idx(d: date_cls, df: date_cls, interval: str) -> int:
    if interval == "day":
        return (d - df).days
    if interval == "week":
        start = df - timedelta(days=df.weekday())
        return (d - start).days // 7
    if interval == "month":
        return (d.year - df.year) * 12 + (d.month - df.month)
    return 0


def _generate_buckets(df: date_cls, dt: date_cls, interval: str) -> list[date_cls]:
    if interval == "all":
        return [df]
    buckets = []
    cur = df
    if interval == "week":
        cur = df - timedelta(days=df.weekday())
    elif interval == "month":
        cur = df.replace(day=1)
    while cur <= dt:
        buckets.append(cur)
        if interval == "day":
            cur += timedelta(days=1)
        elif interval == "week":
            cur += timedelta(days=7)
        elif interval == "month":
            cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
    return buckets


@router.get("/series", response_model=SeriesResponse)
async def get_series(
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    metrics_keys: list[str] = Query(...),
    interval: Literal["day", "week", "month"] = "day",
    date_from: date_cls | None = None,
    date_to: date_cls | None = None,
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SeriesResponse:
    today = datetime.now(UTC).date()
    if not date_to:
        date_to = today
    if not date_from:
        date_from = date_to - timedelta(days=days)

    # Список кабинетов
    accessible = await get_accessible_cabinet_ids(db, current_user)
    if cabinet_ids:
        cabs_q = select(OzonAccount.id).where(
            OzonAccount.id.in_(cabinet_ids),
            OzonAccount.company_id == current_user.company_id,
        )
        if accessible is not None:
            cabs_q = cabs_q.where(OzonAccount.id.in_(accessible))
        ok = (await db.execute(cabs_q)).scalars().all()
        cabs = list(ok)
    else:
        cabs_q = select(OzonAccount.id).where(
            OzonAccount.company_id == current_user.company_id,
            OzonAccount.deleted_at.is_(None),
        )
        if accessible is not None:
            cabs_q = cabs_q.where(OzonAccount.id.in_(accessible))
        cabs = (await db.execute(cabs_q)).scalars().all()

    if not cabs:
        return SeriesResponse(interval=interval, points=[])

    daily = await _fetch_daily_cabinet(db, cabs, date_from, date_to)
    buckets = _generate_buckets(date_from, date_to, interval)

    chosen = [METRICS_BY_KEY[k] for k in metrics_keys if k in METRICS_BY_KEY]

    # Для каждого бакета — собираем daily-row'ы и сворачиваем по каждой метрике
    out: list[SeriesPoint] = []
    for bi, bstart in enumerate(buckets):
        bucket_data: dict[str, list[dict]] = {m.key: [] for m in chosen}
        for d, m in daily.items():
            if d < date_from or d > date_to:
                continue
            if _bucket_idx(d, date_from, interval) != bi:
                continue
            for met in chosen:
                v = m.get(met.key)
                w = m.get(met.weight_by) if met.weight_by else 1
                bucket_data[met.key].append({"value": v, "weight": w})
        values: dict[str, float | None] = {}
        for met in chosen:
            values[met.key] = aggregate_bucket(met, bucket_data[met.key])
        # Метка даты бакета
        if interval == "day":
            label = bstart.strftime("%d.%m")
        elif interval == "week":
            label = bstart.strftime("%d.%m")
        else:
            label = bstart.strftime("%b %Y")
        out.append(SeriesPoint(date=label, values=values))

    return SeriesResponse(interval=interval, points=out)
