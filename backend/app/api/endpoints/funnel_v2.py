"""
Funnel v2 — 5 шагов + рекламная колонка + ДРР + drill-down + comparison.
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import AnalyticsDaily, OzonAccount, Product, Transaction, User

router = APIRouter()
UTC = timezone.utc


class FunnelKPI(BaseModel):
    impressions: int
    clicks: int
    to_cart: int
    orders: int
    delivered: int
    revenue: float
    cart_conv_pct: float | None
    order_conv_pct: float | None
    delivery_conv_pct: float | None
    overall_conv_pct: float | None
    ctr_pct: float | None
    click_to_cart_pct: float | None


class AdBreakdownRow(BaseModel):
    op_type: str
    label: str
    amount: float
    pct_of_total: float
    model: str  # CPC / CPA / FIXED


class AdBlock(BaseModel):
    total_spend: float
    drr_pct: float | None
    breakdown: list[AdBreakdownRow]
    has_data: bool


class FunnelV2Resp(BaseModel):
    period_from: str
    period_to: str
    product_id: str | None
    product_name: str | None
    has_data: bool
    kpi: FunnelKPI
    prev_kpi: FunnelKPI | None
    ad: AdBlock


class FunnelDailyPoint(BaseModel):
    date: str
    impressions: int
    impressions_search: int
    impressions_pdp: int
    clicks: int
    to_cart: int
    to_cart_search: int
    to_cart_pdp: int
    orders: int
    delivered: int
    returns: int
    revenue: float
    overall_conv_pct: float | None
    ctr_pct: float | None
    cart_conv_pct: float | None
    order_conv_pct: float | None
    delivery_conv_pct: float | None


class BestWorstDay(BaseModel):
    date: str
    from_value: int
    to_value: int
    conv_pct: float
    revenue: float


# === AD types Ozon ===
AD_OP_TYPES = [
    ("OperationMarketplaceCostPerClick",            "Трафареты (за клик)",      "CPC"),
    ("OperationPromotionWithCostPerOrder",          "Продвижение за заказ",     "CPA"),
    ("OperationElectronicServicesPromotionInS",     "Продвижение в поиске",     "CPC"),
    ("OperationGettingToTheTop",                    "Вывод в топ",              "FIXED"),
    ("OperationElectronicServiceStencil",           "Трафареты (классические)", "CPC"),
    ("OperationMarketPlaceItemPinReview",           "Закрепление отзыва",       "FIXED"),
    ("OperationLabelOriginal",                      "Бейдж Оригинал",           "FIXED"),
    ("MarketplaceMarketingActionCostOperation",     "Маркетинговые акции",      "CPA"),
    ("OperationOtherElectronicServices",            "Прочие услуги",            "FIXED"),
]


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


def _safe_pct(num: int | float, denom: int | float) -> float | None:
    return round(num / denom * 100, 2) if denom else None


def _kpi(row) -> FunnelKPI:
    imp = int(row.imp or 0)
    clicks = int(row.clicks or 0)
    cart = int(row.cart or 0)
    orders = int(row.orders or 0)
    deliv = int(row.deliv or 0)
    return FunnelKPI(
        impressions=imp, clicks=clicks, to_cart=cart, orders=orders, delivered=deliv,
        revenue=float(row.revenue or 0),
        cart_conv_pct=_safe_pct(cart, imp),
        order_conv_pct=_safe_pct(orders, cart),
        delivery_conv_pct=_safe_pct(deliv, orders),
        overall_conv_pct=_safe_pct(deliv, imp),
        ctr_pct=_safe_pct(clicks, imp),
        click_to_cart_pct=_safe_pct(cart, clicks),
    )


async def _aggregate(
    db: AsyncSession,
    *,
    accs: list[uuid.UUID],
    product_id: uuid.UUID | None,
    date_from: date_cls,
    date_to: date_cls,
):
    where = [
        Product.ozon_account_id.in_(accs),
        AnalyticsDaily.date >= date_from,
        AnalyticsDaily.date <= date_to,
    ]
    if product_id:
        where.append(AnalyticsDaily.product_id == product_id)
    q = select(
        func.coalesce(func.sum(AnalyticsDaily.hits_view_search + AnalyticsDaily.hits_view_pdp), 0).label("imp"),
        func.coalesce(func.sum(AnalyticsDaily.session_view_search + AnalyticsDaily.session_view_pdp), 0).label("clicks"),
        func.coalesce(func.sum(AnalyticsDaily.hits_tocart_search + AnalyticsDaily.hits_tocart_pdp), 0).label("cart"),
        func.coalesce(func.sum(AnalyticsDaily.ordered_units), 0).label("orders"),
        func.coalesce(func.sum(AnalyticsDaily.delivered_units), 0).label("deliv"),
        func.coalesce(func.sum(AnalyticsDaily.revenue), 0).label("revenue"),
    ).select_from(AnalyticsDaily).join(Product, Product.id == AnalyticsDaily.product_id).where(*where)
    return (await db.execute(q)).one()


async def _ad_breakdown(
    db: AsyncSession,
    *,
    accs: list[uuid.UUID],
    date_from: date_cls,
    date_to: date_cls,
    revenue: float,
) -> AdBlock:
    if not accs:
        return AdBlock(total_spend=0, drr_pct=None, breakdown=[], has_data=False)
    dt_from = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
    dt_to = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=UTC)

    op_keys = [op for op, _, _ in AD_OP_TYPES]
    rows = (await db.execute(
        select(
            Transaction.operation_type,
            func.coalesce(func.sum(func.abs(Transaction.amount)), 0).label("amount"),
        )
        .where(
            Transaction.ozon_account_id.in_(accs),
            Transaction.time >= dt_from,
            Transaction.time < dt_to,
            Transaction.operation_type.in_(op_keys),
        )
        .group_by(Transaction.operation_type)
    )).all()

    total = sum(float(r.amount or 0) for r in rows)
    by_op = {r.operation_type: float(r.amount or 0) for r in rows}

    breakdown: list[AdBreakdownRow] = []
    for op, label, model in AD_OP_TYPES:
        amount = by_op.get(op, 0)
        if amount > 0:
            breakdown.append(AdBreakdownRow(
                op_type=op,
                label=label,
                amount=round(amount, 2),
                pct_of_total=round(amount / total * 100, 1) if total else 0,
                model=model,
            ))
    breakdown.sort(key=lambda x: x.amount, reverse=True)
    drr = (total / revenue * 100) if revenue else None
    return AdBlock(
        total_spend=round(total, 2),
        drr_pct=round(drr, 2) if drr is not None else None,
        breakdown=breakdown,
        has_data=total > 0,
    )


@router.get("/", response_model=FunnelV2Resp)
async def get_funnel_v2(
    days: int = Query(30, ge=1, le=730),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    product_id: str | None = Query(None),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    compare: str = Query("prev_period"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FunnelV2Resp:
    today = datetime.now(UTC).date()
    if not date_to:
        date_to = today
    if not date_from:
        date_from = date_to - timedelta(days=days)

    accs = await _account_ids(db, company_id=current_user.company_id, cabinet_ids=cabinet_ids)

    pid: uuid.UUID | None = None
    prod_name: str | None = None
    if product_id:
        try:
            pid = uuid.UUID(product_id)
            prod = (await db.execute(select(Product).where(Product.id == pid))).scalar_one_or_none()
            if prod:
                prod_name = prod.name
        except ValueError:
            pid = None

    if not accs:
        empty_kpi = FunnelKPI(
            impressions=0, clicks=0, to_cart=0, orders=0, delivered=0, revenue=0,
            cart_conv_pct=None, order_conv_pct=None,
            delivery_conv_pct=None, overall_conv_pct=None,
            ctr_pct=None, click_to_cart_pct=None,
        )
        empty_ad = AdBlock(total_spend=0, drr_pct=None, breakdown=[], has_data=False)
        return FunnelV2Resp(
            period_from=date_from.isoformat(), period_to=date_to.isoformat(),
            product_id=product_id, product_name=prod_name,
            has_data=False, kpi=empty_kpi, prev_kpi=None, ad=empty_ad,
        )

    row = await _aggregate(db, accs=accs, product_id=pid, date_from=date_from, date_to=date_to)
    kpi = _kpi(row)

    prev_kpi: FunnelKPI | None = None
    if compare != "none":
        span = (date_to - date_from)
        if compare == "year_ago":
            prev_from = date_from - timedelta(days=365)
            prev_to = date_to - timedelta(days=365)
        else:
            prev_from = date_from - span - timedelta(days=1)
            prev_to = date_from - timedelta(days=1)
        prev_row = await _aggregate(db, accs=accs, product_id=pid, date_from=prev_from, date_to=prev_to)
        prev_kpi = _kpi(prev_row)

    ad = await _ad_breakdown(db, accs=accs, date_from=date_from, date_to=date_to, revenue=kpi.revenue)

    return FunnelV2Resp(
        period_from=date_from.isoformat(),
        period_to=date_to.isoformat(),
        product_id=product_id, product_name=prod_name,
        has_data=kpi.impressions > 0 or kpi.orders > 0,
        kpi=kpi, prev_kpi=prev_kpi, ad=ad,
    )


@router.get("/daily", response_model=list[FunnelDailyPoint])
async def get_funnel_daily(
    days: int = Query(30, ge=1, le=365),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    product_id: str | None = Query(None),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FunnelDailyPoint]:
    today = datetime.now(UTC).date()
    if not date_to:
        date_to = today
    if not date_from:
        date_from = date_to - timedelta(days=days)

    accs = await _account_ids(db, company_id=current_user.company_id, cabinet_ids=cabinet_ids)
    if not accs:
        return []

    pid: uuid.UUID | None = None
    if product_id:
        try:
            pid = uuid.UUID(product_id)
        except ValueError:
            pass

    where = [
        Product.ozon_account_id.in_(accs),
        AnalyticsDaily.date >= date_from,
        AnalyticsDaily.date <= date_to,
    ]
    if pid:
        where.append(AnalyticsDaily.product_id == pid)

    rows = (await db.execute(
        select(
            AnalyticsDaily.date.label("d"),
            func.coalesce(func.sum(AnalyticsDaily.hits_view_search), 0).label("imp_s"),
            func.coalesce(func.sum(AnalyticsDaily.hits_view_pdp), 0).label("imp_p"),
            func.coalesce(func.sum(AnalyticsDaily.session_view_search + AnalyticsDaily.session_view_pdp), 0).label("clicks"),
            func.coalesce(func.sum(AnalyticsDaily.hits_tocart_search), 0).label("cart_s"),
            func.coalesce(func.sum(AnalyticsDaily.hits_tocart_pdp), 0).label("cart_p"),
            func.coalesce(func.sum(AnalyticsDaily.ordered_units), 0).label("orders"),
            func.coalesce(func.sum(AnalyticsDaily.delivered_units), 0).label("deliv"),
            func.coalesce(func.sum(AnalyticsDaily.returns), 0).label("returns_"),
            func.coalesce(func.sum(AnalyticsDaily.revenue), 0).label("revenue"),
        )
        .select_from(AnalyticsDaily)
        .join(Product, Product.id == AnalyticsDaily.product_id)
        .where(*where)
        .group_by("d")
        .order_by("d")
    )).all()

    out: list[FunnelDailyPoint] = []
    for r in rows:
        imp_s = int(r.imp_s or 0)
        imp_p = int(r.imp_p or 0)
        imp = imp_s + imp_p
        clicks = int(r.clicks or 0)
        cart_s = int(r.cart_s or 0)
        cart_p = int(r.cart_p or 0)
        cart = cart_s + cart_p
        orders = int(r.orders or 0)
        deliv = int(r.deliv or 0)
        out.append(FunnelDailyPoint(
            date=r.d.isoformat(),
            impressions=imp,
            impressions_search=imp_s,
            impressions_pdp=imp_p,
            clicks=clicks,
            to_cart=cart,
            to_cart_search=cart_s,
            to_cart_pdp=cart_p,
            orders=orders,
            delivered=deliv,
            returns=int(r.returns_ or 0),
            revenue=float(r.revenue or 0),
            overall_conv_pct=_safe_pct(deliv, imp),
            ctr_pct=_safe_pct(clicks, imp),
            cart_conv_pct=_safe_pct(cart, imp),
            order_conv_pct=_safe_pct(orders, cart),
            delivery_conv_pct=_safe_pct(deliv, orders),
        ))
    return out


@router.get("/best-worst-days", response_model=dict)
async def best_worst_days(
    days: int = Query(90, ge=7, le=365),
    metric: str = Query("overall", description="overall|cart|order|delivery"),
    product_id: str | None = Query(None),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    today = datetime.now(UTC).date()
    date_from = today - timedelta(days=days)

    label_map = {
        "cart":     ("Показы",  "В корзину"),
        "order":    ("Корзина", "Заказы"),
        "delivery": ("Заказы",  "Доставлено"),
        "overall":  ("Показы",  "Доставлено"),
    }
    from_label, to_label = label_map.get(metric, label_map["overall"])

    accs = await _account_ids(db, company_id=current_user.company_id, cabinet_ids=cabinet_ids)
    if not accs:
        return {"best": [], "worst": [], "metric": metric, "from_label": from_label, "to_label": to_label}

    pid: uuid.UUID | None = None
    if product_id:
        try:
            pid = uuid.UUID(product_id)
        except ValueError:
            pass

    where = [
        Product.ozon_account_id.in_(accs),
        AnalyticsDaily.date >= date_from,
    ]
    if pid:
        where.append(AnalyticsDaily.product_id == pid)

    rows = (await db.execute(
        select(
            AnalyticsDaily.date.label("d"),
            func.coalesce(func.sum(AnalyticsDaily.hits_view_search + AnalyticsDaily.hits_view_pdp), 0).label("imp"),
            func.coalesce(func.sum(AnalyticsDaily.hits_tocart_search + AnalyticsDaily.hits_tocart_pdp), 0).label("cart"),
            func.coalesce(func.sum(AnalyticsDaily.ordered_units), 0).label("orders"),
            func.coalesce(func.sum(AnalyticsDaily.delivered_units), 0).label("deliv"),
            func.coalesce(func.sum(AnalyticsDaily.revenue), 0).label("revenue"),
        )
        .select_from(AnalyticsDaily)
        .join(Product, Product.id == AnalyticsDaily.product_id)
        .where(*where)
        .group_by("d")
    )).all()

    def pick(r) -> BestWorstDay | None:
        imp = int(r.imp or 0)
        cart = int(r.cart or 0)
        orders = int(r.orders or 0)
        deliv = int(r.deliv or 0)
        revenue = float(r.revenue or 0)
        if metric == "cart":
            if imp < 100:
                return None
            return BestWorstDay(date=r.d.isoformat(), from_value=imp, to_value=cart,
                                conv_pct=_safe_pct(cart, imp) or 0, revenue=revenue)
        if metric == "order":
            if cart < 20:
                return None
            return BestWorstDay(date=r.d.isoformat(), from_value=cart, to_value=orders,
                                conv_pct=_safe_pct(orders, cart) or 0, revenue=revenue)
        if metric == "delivery":
            if orders < 5:
                return None
            return BestWorstDay(date=r.d.isoformat(), from_value=orders, to_value=deliv,
                                conv_pct=_safe_pct(deliv, orders) or 0, revenue=revenue)
        if imp < 100:
            return None
        return BestWorstDay(date=r.d.isoformat(), from_value=imp, to_value=deliv,
                            conv_pct=_safe_pct(deliv, imp) or 0, revenue=revenue)

    items = [p for r in rows if (p := pick(r))]
    items.sort(key=lambda x: x.conv_pct, reverse=True)
    best = items[:5]
    worst = sorted(items, key=lambda x: x.conv_pct)[:5]

    return {
        "best": [b.dict() for b in best],
        "worst": [w.dict() for w in worst],
        "metric": metric,
        "from_label": from_label,
        "to_label": to_label,
    }
