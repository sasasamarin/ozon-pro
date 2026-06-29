"""
/products/stats — «Статистика товара» (#94 + #93 + Маркеры).

Матрица «метрика × период» по одному товару:
- GET  /matrix       — данные матрицы (interval=day/week/month/all)
- GET  /metrics      — список 45 метрик с описанием
- GET  /templates    — шаблоны наборов
- POST /templates    — создать
- PATCH /templates/{id} — обновить
- DELETE /templates/{id} — удалить
- GET  /markers      — маркеры дней (для product + date range)
- POST /markers      — создать
- DELETE /markers/{id} — удалить

Логика свёртки:
- day: 1 значение в день (как есть)
- week: понедельная свёртка с правильной aggregation
- month: помесячная свёртка
- all: одна цифра за весь период
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.deps_cabinets import get_accessible_cabinet_ids, verify_cabinet_access
from app.db.session import get_db
from app.models import DayMarker, MetricTemplate, OzonAccount, Product, User
from app.services.product_metrics import (
    METRIC_GROUPS,
    METRICS,
    METRICS_BY_KEY,
    Metric,
    aggregate_bucket,
)

router = APIRouter()
UTC = timezone.utc


# ============================================================
# Schemas
# ============================================================


class MetricInfo(BaseModel):
    key: str
    label: str
    group: str
    description: str
    source: str
    format: str
    agg: str


class MatrixCell(BaseModel):
    value: float | None


class MatrixRow(BaseModel):
    metric: MetricInfo
    total: float | None              # значение за весь период
    cells: list[float | None]        # значения по бакетам


class MatrixResponse(BaseModel):
    product_id: str
    product_name: str
    offer_id: str
    interval: str
    bucket_labels: list[str]         # даты или метки бакетов
    bucket_dates: list[str]          # фактические даты-границы (для маркеров)
    rows: list[MatrixRow]
    markers_by_date: dict[str, list[dict]]  # {ISO-date: [{id, text}, ...]}


class TemplateIn(BaseModel):
    name: str
    metrics: list[str]


class TemplateRow(BaseModel):
    id: str
    name: str
    metrics: list[str]


class MarkerIn(BaseModel):
    product_id: uuid.UUID | None = None
    cabinet_id: uuid.UUID | None = None
    marker_date: date_cls
    text: str = Field(..., min_length=1, max_length=500)


class MarkerRow(BaseModel):
    id: str
    product_id: str | None
    cabinet_id: str | None
    marker_date: str
    text: str


# ============================================================
# Helpers
# ============================================================


def _bucket_for_date(d: date_cls, interval: str) -> tuple[date_cls, str]:
    """Возвращает (bucket_start, label) для day/week/month/all."""
    if interval == "day":
        return d, d.isoformat()
    if interval == "week":
        # ISO week — понедельник
        start = d - timedelta(days=d.weekday())
        return start, f"{start.isoformat()} нед"
    if interval == "month":
        start = d.replace(day=1)
        return start, start.strftime("%Y-%m")
    # all
    return date_cls(1970, 1, 1), "Весь период"


def _generate_buckets(date_from: date_cls, date_to: date_cls, interval: str) -> list[date_cls]:
    """Список бакетов по интервалу."""
    if interval == "all":
        return [date_cls(1970, 1, 1)]
    buckets = []
    cur = date_from
    if interval == "week":
        cur = date_from - timedelta(days=date_from.weekday())
    elif interval == "month":
        cur = date_from.replace(day=1)
    while cur <= date_to:
        buckets.append(cur)
        if interval == "day":
            cur += timedelta(days=1)
        elif interval == "week":
            cur += timedelta(days=7)
        elif interval == "month":
            cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
    return buckets


async def _fetch_product_owned(
    db: AsyncSession,
    product_id: uuid.UUID,
    company_id: uuid.UUID,
    user: User | None = None,
) -> Product:
    q = select(Product).join(OzonAccount, OzonAccount.id == Product.ozon_account_id) \
        .where(Product.id == product_id, OzonAccount.company_id == company_id)
    if user is not None:
        accessible = await get_accessible_cabinet_ids(db, user)
        if accessible is not None:
            q = q.where(OzonAccount.id.in_(accessible))
    p = (await db.execute(q)).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Товар не найден")
    return p


async def _fetch_daily_metrics(
    db: AsyncSession,
    product_id: uuid.UUID,
    date_from: date_cls,
    date_to: date_cls,
) -> dict[date_cls, dict[str, float | None]]:
    """
    Тянет ВСЕ метрики по дням за окно. Возвращает {date: {metric_key: value}}.

    Источники: analytics_daily, ad_statistics, orders+order_items, returns,
    cancellations, stocks (snapshot), products+cost_history.
    """
    rows: dict[date_cls, dict[str, float | None]] = {}

    def _ensure(d: date_cls) -> dict:
        if d not in rows:
            rows[d] = {}
        return rows[d]

    # 1. analytics_daily — ТОЛЬКО UX-метрики воронки (показы / клики / корзина).
    # Они приходят от Ozon Аналитики с лагом 1-2 дня — это нормально.
    # Заказы / выкуплено / выручка для свежих дней лагают (вчера обычно
    # ordered_units=0) — поэтому берём из order_items (sync ежечасный, в реалтайме).
    ad_rows = (await db.execute(text("""
        SELECT date,
               COALESCE(hits_view_search, 0) AS impressions,
               COALESCE(hits_view_search,0) + COALESCE(hits_view_pdp,0) AS impressions_legacy,
               COALESCE(hits_view_search,0) AS imp_search,
               COALESCE(hits_view_pdp,0) AS imp_pdp,
               COALESCE(hits_view_pdp, 0) AS clicks,
               COALESCE(hits_tocart_search,0)+COALESCE(hits_tocart_pdp,0) AS cart_count,
               COALESCE(position_category,0)::float AS position_search
        FROM analytics_daily WHERE product_id = :pid AND date >= :df AND date <= :dt
    """), {"pid": str(product_id), "df": date_from, "dt": date_to})).all()
    for r in ad_rows:
        d = _ensure(r.date)
        d["impressions"] = float(r.impressions or 0)
        d["impressions_legacy"] = float(r.impressions_legacy or 0)
        d["imp_search"] = float(r.imp_search or 0)
        d["imp_pdp"] = float(r.imp_pdp or 0)
        d["clicks"] = float(r.clicks or 0)
        d["cart_count"] = float(r.cart_count or 0)
        d["position_search"] = float(r.position_search or 0) or None

    # 1b. orders + order_items — РЕАЛЬНЫЕ заказы и выкуп (свежие).
    # Совпадает с Ozon Seller UI «Заказы» 1:1.
    orders_rows = (await db.execute(text("""
        SELECT DATE(o.order_created_at) AS d,
               SUM(oi.quantity) AS orders_qty,
               SUM(oi.quantity) FILTER (WHERE o.status = 'delivered') AS delivered_qty,
               SUM(oi.quantity) FILTER (WHERE o.status = 'cancelled') AS cancelled_qty,
               SUM(oi.quantity) FILTER (WHERE o.status IN ('awaiting_packaging','awaiting_deliver','delivering','arrived')) AS pending_qty,
               SUM(oi.price * oi.quantity)::float AS revenue
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE oi.product_id = :pid
          AND o.order_created_at >= :df
          AND o.order_created_at < (CAST(:dt AS date) + INTERVAL '1 day')
        GROUP BY 1
    """), {"pid": str(product_id), "df": date_from, "dt": date_to})).all()
    for r in orders_rows:
        d = _ensure(r.d)
        d["orders"] = float(r.orders_qty or 0)
        d["delivered"] = float(r.delivered_qty or 0)
        d["cancelled"] = float(r.cancelled_qty or 0)
        d["pending_decision"] = float(r.pending_qty or 0)
        d["revenue"] = float(r.revenue or 0)

    # 1c. returns — выкуплено и вернули (по дате возврата)
    returns_rows = (await db.execute(text("""
        SELECT DATE(return_date) AS d, SUM(quantity)::float AS returned_qty
        FROM returns
        WHERE product_id = :pid
          AND return_date >= :df AND return_date <= :dt
        GROUP BY 1
    """), {"pid": str(product_id), "df": date_from, "dt": date_to})).all()
    for r in returns_rows:
        d = _ensure(r.d)
        d["returned_after"] = float(r.returned_qty or 0)

    # 2. ad_statistics — реклама
    ad_stat = (await db.execute(text("""
        SELECT date,
               SUM(impressions)::float AS imp,
               SUM(clicks)::float AS clicks,
               SUM(orders)::float AS orders,
               SUM(spend)::float AS spend,
               SUM(revenue)::float AS rev
        FROM ad_statistics WHERE product_id = :pid AND date >= :df AND date <= :dt
        GROUP BY date
    """), {"pid": str(product_id), "df": date_from, "dt": date_to})).all()
    for r in ad_stat:
        d = _ensure(r.date)
        d["ad_impressions"] = float(r.imp or 0)
        d["ad_clicks"] = float(r.clicks or 0)
        d["ad_orders"] = float(r.orders or 0)
        d["ad_spend"] = float(r.spend or 0)

    # 3. Цены — средневзвешенные по qty за день
    price_rows = (await db.execute(text("""
        SELECT DATE(o.order_created_at) d,
               AVG(oi.price)::float AS avg_price,
               SUM(oi.customer_price * oi.quantity)::float / NULLIF(SUM(oi.quantity), 0) AS avg_cp
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE oi.product_id = :pid
          AND o.order_created_at >= :df AND o.order_created_at < (CAST(:dt AS date) + INTERVAL '1 day')
        GROUP BY 1
    """), {"pid": str(product_id), "df": date_from, "dt": date_to})).all()
    for r in price_rows:
        d = _ensure(r.d)
        d["seller_price"] = float(r.avg_price or 0) or None
        d["customer_price"] = float(r.avg_cp or 0) or None

    # 3b. product_queries_daily — Premium Plus: семантика товара
    pq_rows = (await db.execute(text("""
        SELECT date,
               unique_search_users::float AS usu,
               unique_view_users::float AS uvu,
               position::float AS pos,
               view_conversion::float AS vc,
               gmv::float AS gmv
        FROM product_queries_daily
        WHERE product_id = :pid AND date >= :df AND date <= :dt
    """), {"pid": str(product_id), "df": date_from, "dt": date_to})).all()
    for r in pq_rows:
        d = _ensure(r.date)
        d["unique_search_users"] = float(r.usu or 0) or None
        d["unique_view_users"] = float(r.uvu or 0) or None
        d["search_position"] = float(r.pos or 0) or None
        d["search_view_conversion"] = float(r.vc or 0) or None
        d["search_gmv"] = float(r.gmv or 0)

    # 3c. realization_daily — Premium Plus: точная посуточная реализация
    rd_rows = (await db.execute(text("""
        SELECT day, qty_sold::float AS qty, weighted_cp::float AS cp,
               sum_bonus::float AS bonus, sum_fee::float AS fee
        FROM realization_daily
        WHERE product_id = :pid AND day >= :df AND day <= :dt
    """), {"pid": str(product_id), "df": date_from, "dt": date_to})).all()
    for r in rd_rows:
        d = _ensure(r.day)
        d["realization_qty"] = float(r.qty or 0)
        d["realization_avg_cp"] = float(r.cp or 0) or None
        d["realization_bonus"] = float(r.bonus or 0)
        d["realization_fee"] = float(r.fee or 0)

    # 4. stocks — последний снимок дня
    stocks_rows = (await db.execute(text("""
        SELECT DATE(time) d,
               SUM(free_to_sell)::float AS free,
               SUM(in_transit)::float AS in_t,
               SUM(reserved)::float AS reserved
        FROM stocks WHERE product_id = :pid AND time >= :df AND time < (CAST(:dt AS date) + INTERVAL '1 day')
        GROUP BY 1
    """), {"pid": str(product_id), "df": date_from, "dt": date_to})).all()
    for r in stocks_rows:
        d = _ensure(r.d)
        d["stock_warehouse"] = float(r.free or 0)
        d["in_transit_to"] = float(r.in_t or 0)

    # 5. Derived metrics (после загрузки сырых)
    for d, m in rows.items():
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


# ============================================================
# Endpoints
# ============================================================


@router.get("/metrics", response_model=list[MetricInfo])
async def list_metrics(current_user: User = Depends(get_current_user)) -> list[MetricInfo]:
    return [MetricInfo(
        key=m.key, label=m.label, group=m.group, description=m.description,
        source=m.source, format=m.format, agg=m.agg,
    ) for m in METRICS]


@router.get("/matrix", response_model=MatrixResponse)
async def get_matrix(
    product_id: uuid.UUID,
    interval: Literal["day", "week", "month", "all"] = "day",
    date_from: date_cls | None = None,
    date_to: date_cls | None = None,
    days: int = 30,
    metrics_keys: list[str] | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MatrixResponse:
    today = datetime.now(UTC).date()
    if not date_to:
        date_to = today
    if not date_from:
        date_from = date_to - timedelta(days=days)

    product = await _fetch_product_owned(db, product_id, current_user.company_id, current_user)

    # Какие метрики возвращаем (если не задано — все)
    keys = metrics_keys or [m.key for m in METRICS]
    chosen = [METRICS_BY_KEY[k] for k in keys if k in METRICS_BY_KEY]

    # Сырые дневные данные
    daily = await _fetch_daily_metrics(db, product_id, date_from, date_to)

    # Бакеты
    buckets = _generate_buckets(date_from, date_to, interval)
    bucket_labels = []
    bucket_dates = []
    for b in buckets:
        if interval == "day":
            bucket_labels.append(b.strftime("%d.%m"))
        elif interval == "week":
            bucket_labels.append(b.strftime("%d.%m") + "–")
        elif interval == "month":
            bucket_labels.append(b.strftime("%b %Y"))
        else:
            bucket_labels.append("Весь период")
        bucket_dates.append(b.isoformat())

    # Свёртка: для каждого бакета — список daily_rows этого бакета
    def _bucket_idx(d: date_cls) -> int:
        if interval == "day":
            return (d - date_from).days
        if interval == "week":
            start = date_from - timedelta(days=date_from.weekday())
            return (d - start).days // 7
        if interval == "month":
            return (d.year - date_from.year) * 12 + (d.month - date_from.month)
        return 0

    rows_out: list[MatrixRow] = []
    for m in chosen:
        # Собираем daily_rows для каждого бакета
        bucket_data: list[list[dict]] = [[] for _ in buckets]
        total_data: list[dict] = []
        for d in sorted(daily.keys()):
            if d < date_from or d > date_to:
                continue
            val = daily[d].get(m.key)
            weight = daily[d].get(m.weight_by) if m.weight_by else 1
            row = {"value": val, "weight": weight}
            idx = _bucket_idx(d)
            if 0 <= idx < len(buckets):
                bucket_data[idx].append(row)
            total_data.append(row)

        cells = [aggregate_bucket(m, br) for br in bucket_data]
        total = aggregate_bucket(m, total_data)
        rows_out.append(MatrixRow(
            metric=MetricInfo(
                key=m.key, label=m.label, group=m.group, description=m.description,
                source=m.source, format=m.format, agg=m.agg,
            ),
            total=total,
            cells=cells,
        ))

    # Маркеры
    markers = (await db.execute(
        select(DayMarker).where(
            DayMarker.company_id == current_user.company_id,
            DayMarker.marker_date >= date_from,
            DayMarker.marker_date <= date_to,
            (DayMarker.product_id == product_id) | (DayMarker.product_id.is_(None)),
        )
    )).scalars().all()
    markers_by_date: dict[str, list[dict]] = {}
    for mk in markers:
        d = mk.marker_date.isoformat()
        markers_by_date.setdefault(d, []).append({
            "id": str(mk.id), "text": mk.text,
        })

    return MatrixResponse(
        product_id=str(product.id),
        product_name=product.name or "",
        offer_id=product.offer_id or "",
        interval=interval,
        bucket_labels=bucket_labels,
        bucket_dates=bucket_dates,
        rows=rows_out,
        markers_by_date=markers_by_date,
    )


# ============================================================
# Templates CRUD
# ============================================================


@router.get("/templates", response_model=list[TemplateRow])
async def list_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TemplateRow]:
    rows = (await db.execute(
        select(MetricTemplate).where(MetricTemplate.company_id == current_user.company_id)
        .order_by(MetricTemplate.created_at.desc())
    )).scalars().all()
    return [TemplateRow(id=str(t.id), name=t.name, metrics=list(t.metrics)) for t in rows]


@router.post("/templates", response_model=TemplateRow)
async def create_template(
    payload: TemplateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateRow:
    t = MetricTemplate(
        company_id=current_user.company_id, user_id=current_user.id,
        name=payload.name, metrics=payload.metrics,
    )
    db.add(t); await db.commit(); await db.refresh(t)
    return TemplateRow(id=str(t.id), name=t.name, metrics=list(t.metrics))


@router.patch("/templates/{tid}", response_model=TemplateRow)
async def update_template(
    tid: uuid.UUID, payload: TemplateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateRow:
    t = (await db.execute(
        select(MetricTemplate).where(
            MetricTemplate.id == tid, MetricTemplate.company_id == current_user.company_id
        )
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Шаблон не найден")
    t.name = payload.name; t.metrics = payload.metrics
    await db.commit()
    return TemplateRow(id=str(t.id), name=t.name, metrics=list(t.metrics))


@router.delete("/templates/{tid}", status_code=204)
async def delete_template(
    tid: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.execute(delete(MetricTemplate).where(
        MetricTemplate.id == tid, MetricTemplate.company_id == current_user.company_id
    ))
    await db.commit()


# ============================================================
# Markers CRUD
# ============================================================


@router.get("/markers", response_model=list[MarkerRow])
async def list_markers(
    product_id: uuid.UUID | None = None,
    date_from: date_cls | None = None,
    date_to: date_cls | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MarkerRow]:
    q = select(DayMarker).where(DayMarker.company_id == current_user.company_id)
    if product_id:
        q = q.where((DayMarker.product_id == product_id) | (DayMarker.product_id.is_(None)))
    if date_from:
        q = q.where(DayMarker.marker_date >= date_from)
    if date_to:
        q = q.where(DayMarker.marker_date <= date_to)
    rows = (await db.execute(q.order_by(DayMarker.marker_date.desc()))).scalars().all()
    return [
        MarkerRow(
            id=str(m.id),
            product_id=str(m.product_id) if m.product_id else None,
            cabinet_id=str(m.cabinet_id) if m.cabinet_id else None,
            marker_date=m.marker_date.isoformat(),
            text=m.text,
        )
        for m in rows
    ]


@router.post("/markers", response_model=MarkerRow)
async def create_marker(
    payload: MarkerIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MarkerRow:
    if payload.cabinet_id:
        await verify_cabinet_access(db, current_user, payload.cabinet_id)
    if payload.product_id:
        await _fetch_product_owned(
            db, payload.product_id, current_user.company_id, current_user,
        )
    m = DayMarker(
        company_id=current_user.company_id, user_id=current_user.id,
        product_id=payload.product_id, cabinet_id=payload.cabinet_id,
        marker_date=payload.marker_date, text=payload.text,
    )
    db.add(m); await db.commit(); await db.refresh(m)
    return MarkerRow(
        id=str(m.id),
        product_id=str(m.product_id) if m.product_id else None,
        cabinet_id=str(m.cabinet_id) if m.cabinet_id else None,
        marker_date=m.marker_date.isoformat(),
        text=m.text,
    )


@router.delete("/markers/{mid}", status_code=204)
async def delete_marker(
    mid: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.execute(delete(DayMarker).where(
        DayMarker.id == mid, DayMarker.company_id == current_user.company_id
    ))
    await db.commit()
