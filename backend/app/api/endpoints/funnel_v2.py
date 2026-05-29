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
from app.models import (
    AdCampaign,
    AdStatistics,
    AnalyticsDaily,
    OzonAccount,
    Product,
    Transaction,
    User,
)

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


# =====================================================================
# КОММИТ 3: графики взаимосвязей
# =====================================================================

import math


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    sxx = sum((xs[i] - mx) ** 2 for i in range(n))
    syy = sum((ys[i] - my) ** 2 for i in range(n))
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _strength_label_ru(r: float | None) -> str:
    if r is None:
        return "недостаточно данных"
    a = abs(r)
    if a >= 0.7:
        return "Сильная связь"
    if a >= 0.4:
        return "Умеренная связь"
    if a >= 0.2:
        return "Слабая связь"
    return "Связи практически нет"


def _log_elasticity(xs: list[float], ys: list[float]) -> float | None:
    """β из log(y)=α+β·log(x) — «+1% показов → +β% заказов»."""
    px = [math.log(v) for v in xs if v > 0]
    py = [math.log(ys[i]) for i, v in enumerate(xs) if v > 0 and ys[i] > 0]
    # выровнять — фильтруем те же индексы
    pairs = [(math.log(xs[i]), math.log(ys[i])) for i in range(len(xs)) if xs[i] > 0 and ys[i] > 0]
    if len(pairs) < 5:
        return None
    lx = [p[0] for p in pairs]
    ly = [p[1] for p in pairs]
    n = len(pairs)
    mx = sum(lx) / n
    my = sum(ly) / n
    num = sum((lx[i] - mx) * (ly[i] - my) for i in range(n))
    den = sum((lx[i] - mx) ** 2 for i in range(n))
    if den == 0:
        return None
    return num / den


class CorrPoint(BaseModel):
    date: str
    impressions: int
    orders: int


class LagCorr(BaseModel):
    lag_days: int
    r: float | None


class CorrelationsResp(BaseModel):
    period_from: str
    period_to: str
    series: list[CorrPoint]
    r: float | None
    elasticity: float | None
    lags: list[LagCorr]
    best_lag_days: int | None
    headline: str
    explanation: str


@router.get("/correlations", response_model=CorrelationsResp)
async def funnel_correlations(
    days: int = Query(28, ge=14, le=365),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    product_id: str | None = Query(None),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CorrelationsResp:
    """Корреляция Показы↔Заказы по дням + лаг-анализ + регрессия."""
    today = datetime.now(UTC).date()
    if not date_to:
        date_to = today
    if not date_from:
        date_from = date_to - timedelta(days=days)

    accs = await _account_ids(db, company_id=current_user.company_id, cabinet_ids=cabinet_ids)
    if not accs:
        return CorrelationsResp(
            period_from=date_from.isoformat(), period_to=date_to.isoformat(),
            series=[], r=None, elasticity=None, lags=[], best_lag_days=None,
            headline="Нет данных",
            explanation="Подключите хотя бы один кабинет Ozon — без него нечего сопоставлять.",
        )

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
            func.coalesce(func.sum(AnalyticsDaily.hits_view_search + AnalyticsDaily.hits_view_pdp), 0).label("imp"),
            func.coalesce(func.sum(AnalyticsDaily.ordered_units), 0).label("orders"),
        )
        .select_from(AnalyticsDaily)
        .join(Product, Product.id == AnalyticsDaily.product_id)
        .where(*where)
        .group_by("d")
        .order_by("d")
    )).all()

    series = [
        CorrPoint(date=r.d.isoformat(), impressions=int(r.imp or 0), orders=int(r.orders or 0))
        for r in rows
    ]
    imps = [float(p.impressions) for p in series]
    ords = [float(p.orders) for p in series]
    r0 = _pearson(imps, ords)
    beta = _log_elasticity(imps, ords)

    # Лаг-корреляция: импрессии (i) ↔ заказы (i+lag). Если лаг=1 — заказы завтра.
    lags: list[LagCorr] = []
    best_lag = 0
    best_abs = abs(r0) if r0 is not None else -1.0
    for lag in (0, 1, 2, 3):
        if lag == 0:
            r_lag = r0
        else:
            if len(imps) <= lag:
                r_lag = None
            else:
                xs = imps[: len(imps) - lag]
                ys = ords[lag:]
                r_lag = _pearson(xs, ys)
        lags.append(LagCorr(lag_days=lag, r=round(r_lag, 4) if r_lag is not None else None))
        if r_lag is not None and abs(r_lag) > best_abs:
            best_abs = abs(r_lag)
            best_lag = lag

    headline = _strength_label_ru(r0)
    if not imps or not ords or len(imps) < 3:
        explanation = "Недостаточно дней для расчёта (нужно ≥3)."
    else:
        parts: list[str] = []
        if r0 is not None:
            parts.append(f"Коэффициент Пирсона r = {r0:.2f}")
        if beta is not None:
            sign = "+" if beta > 0 else ""
            parts.append(f"эластичность β = {beta:.2f} (рост показов на 10% → заказы {sign}{beta * 10:.1f}%)")
        if best_lag > 0:
            parts.append(f"эффект сильнее всего проявляется через {best_lag} дн.")
        elif r0 is not None and abs(r0) >= 0.4:
            parts.append("эффект мгновенный (тот же день)")
        explanation = "; ".join(parts) + "."

    return CorrelationsResp(
        period_from=date_from.isoformat(),
        period_to=date_to.isoformat(),
        series=series,
        r=round(r0, 4) if r0 is not None else None,
        elasticity=round(beta, 4) if beta is not None else None,
        lags=lags,
        best_lag_days=best_lag if best_lag > 0 else (0 if r0 is not None else None),
        headline=headline,
        explanation=explanation,
    )


# === Реклама → Заказы по типам ===========================================

# Маппинг для группировки op_type из transactions в наши «модели оплаты».
_TX_OP_TYPE_TO_GROUP = {
    "OperationMarketplaceCostPerClick":         ("Трафареты (CPC)",               "PER_CLICK"),
    "OperationElectronicServiceStencil":        ("Трафареты (классические CPC)",  "PER_CLICK"),
    "OperationElectronicServicesPromotionInS":  ("Продвижение в поиске",          "PER_ORDER"),
    "OperationPromotionWithCostPerOrder":       ("Продвижение за заказ",          "PER_ORDER"),
    "MarketplaceMarketingActionCostOperation":  ("Маркетинговые акции",           "PER_ORDER"),
    "OperationLabelOriginal":                   ("Бейдж Оригинал",                "FIXED"),
    "OperationGettingToTheTop":                 ("Вывод в топ",                   "FIXED"),
    "OperationMarketPlaceItemPinReview":        ("Закрепление отзыва",            "FIXED"),
    "OperationOtherElectronicServices":         ("Прочие услуги",                 "FIXED"),
}

# Маппинг campaign_type из ad_campaigns → русская метка для PA-источника
_CAMPAIGN_TYPE_LABEL = {
    "sku":          ("Трафареты (SKU)",       "PER_CLICK"),
    "search_promo": ("Продвижение в поиске",  "PER_ORDER"),
    "banner":       ("Баннеры",               "CPM"),
    "brand_shelf":  ("Брендовая полка",       "FIXED"),
    "ref_vk":       ("Реф. ВК",               "PER_CLICK"),
    "video_banner": ("Видеобаннеры",          "CPM"),
    "global_promo": ("Глобальные акции",      "FIXED"),
    "unknown":      ("Другое (новые типы)",   "?"),
}


class AdTypeDaily(BaseModel):
    date: str
    spend: float
    orders: int
    revenue: float


class AdTypeRow(BaseModel):
    type_key: str           # 'sku' | 'search_promo' | ...
    label: str
    payment_model: str      # PER_CLICK / PER_ORDER / CPM / FIXED / ?
    source: str             # 'PA-daily' | 'transactions-only'
    spend: float
    revenue: float
    orders: int
    drr_pct: float | None
    daily: list[AdTypeDaily]
    unknown_ozon_types: list[str]   # реальные advObjectType если source 'unknown'


class AdByTypeResp(BaseModel):
    period_from: str
    period_to: str
    rows: list[AdTypeRow]
    total_spend_pa: float
    total_spend_tx: float
    note: str


@router.get("/ad-by-type", response_model=AdByTypeResp)
async def ad_by_type(
    days: int = Query(28, ge=1, le=365),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdByTypeResp:
    """Расход на рекламу разбитый по типам кампаний.
    Источник 1 (daily): ad_statistics — есть только для SKU и search_promo.
    Источник 2 (только total): transactions — единственное что есть для баннеров/брендовой полки.
    """
    today = datetime.now(UTC).date()
    if not date_to:
        date_to = today
    if not date_from:
        date_from = date_to - timedelta(days=days)

    accs = await _account_ids(db, company_id=current_user.company_id, cabinet_ids=cabinet_ids)
    if not accs:
        return AdByTypeResp(
            period_from=date_from.isoformat(), period_to=date_to.isoformat(),
            rows=[], total_spend_pa=0, total_spend_tx=0,
            note="Нет подключённых кабинетов",
        )

    # === PA daily через ad_statistics ↔ ad_campaigns
    pa_rows = (await db.execute(
        select(
            AdCampaign.campaign_type.label("ct"),
            AdStatistics.date.label("d"),
            func.coalesce(func.sum(AdStatistics.spend), 0).label("spend"),
            func.coalesce(func.sum(AdStatistics.revenue), 0).label("rev"),
            func.coalesce(func.sum(AdStatistics.orders), 0).label("ord"),
        )
        .select_from(AdStatistics)
        .join(AdCampaign, AdCampaign.ozon_campaign_id == AdStatistics.ozon_campaign_id)
        .where(
            AdStatistics.ozon_account_id.in_(accs),
            AdStatistics.date >= date_from,
            AdStatistics.date <= date_to,
        )
        .group_by(AdCampaign.campaign_type, AdStatistics.date)
        .order_by(AdCampaign.campaign_type, AdStatistics.date)
    )).all()

    pa_by_type: dict[str, dict] = {}
    for r in pa_rows:
        ct = r.ct
        bucket = pa_by_type.setdefault(ct, {
            "spend": 0.0, "rev": 0.0, "ord": 0, "daily": []
        })
        spend_d = float(r.spend or 0)
        rev_d = float(r.rev or 0)
        ord_d = int(r.ord or 0)
        bucket["spend"] += spend_d
        bucket["rev"] += rev_d
        bucket["ord"] += ord_d
        bucket["daily"].append(AdTypeDaily(
            date=r.d.isoformat(), spend=round(spend_d, 2),
            orders=ord_d, revenue=round(rev_d, 2),
        ))

    # === transactions total (для баннеров и др., где PA не даёт daily)
    dt_from = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
    dt_to = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    tx_rows = (await db.execute(
        select(
            Transaction.operation_type.label("op"),
            func.coalesce(func.sum(func.abs(Transaction.amount)), 0).label("spend"),
        )
        .where(
            Transaction.ozon_account_id.in_(accs),
            Transaction.time >= dt_from,
            Transaction.time < dt_to,
            Transaction.operation_type.in_(list(_TX_OP_TYPE_TO_GROUP.keys())),
        )
        .group_by(Transaction.operation_type)
    )).all()
    tx_by_op = {r.op: float(r.spend or 0) for r in tx_rows}

    # === Известные advObjectType из ad_campaigns (для подсветки unknown)
    # raw_data — JSON (не JSONB) → .astext не работает; вытаскиваем в Python
    unk_rows = (await db.execute(
        select(AdCampaign.raw_data).where(
            AdCampaign.ozon_account_id.in_(accs),
            AdCampaign.campaign_type == "unknown",
        )
    )).all()
    unknown_obj_types = sorted({
        (r[0] or {}).get("advObjectType")
        for r in unk_rows if (r[0] or {}).get("advObjectType")
    })

    rows_out: list[AdTypeRow] = []

    # PA-rows: dump as-is per campaign_type
    for ct, b in pa_by_type.items():
        label, pay = _CAMPAIGN_TYPE_LABEL.get(ct, (ct, "?"))
        drr = (b["spend"] / b["rev"] * 100) if b["rev"] else None
        rows_out.append(AdTypeRow(
            type_key=ct, label=label, payment_model=pay,
            source="PA-daily",
            spend=round(b["spend"], 2), revenue=round(b["rev"], 2), orders=b["ord"],
            drr_pct=round(drr, 2) if drr is not None else None,
            daily=b["daily"],
            unknown_ozon_types=unknown_obj_types if ct == "unknown" else [],
        ))

    # === Transactions-only типы: рассчитываем те ops которые НЕ покрылись PA
    # Для это группируем ops в логические группы (CPC, CPA, FIXED) и складываем.
    # Если у нас уже есть soft PA-spend по тем же группам — берём дельту между tx и PA.
    pa_spend_pc = sum(b["spend"] for ct, b in pa_by_type.items()
                       if _CAMPAIGN_TYPE_LABEL.get(ct, (None, "?"))[1] == "PER_CLICK")
    pa_spend_po = sum(b["spend"] for ct, b in pa_by_type.items()
                       if _CAMPAIGN_TYPE_LABEL.get(ct, (None, "?"))[1] == "PER_ORDER")

    # Группируем tx по модели оплаты
    tx_groups: dict[str, dict] = {}
    for op, spend in tx_by_op.items():
        if spend <= 0:
            continue
        label, pay = _TX_OP_TYPE_TO_GROUP[op]
        g = tx_groups.setdefault(pay, {"spend": 0.0, "ops": []})
        g["spend"] += spend
        g["ops"].append((label, spend))

    # Для FIXED-операций PA-данных НЕТ — добавляем как transactions-only
    fixed_g = tx_groups.get("FIXED")
    if fixed_g:
        for label, sp in sorted(fixed_g["ops"], key=lambda x: -x[1]):
            rows_out.append(AdTypeRow(
                type_key=f"tx:{label}", label=label, payment_model="FIXED",
                source="transactions-only",
                spend=round(sp, 2), revenue=0, orders=0, drr_pct=None, daily=[],
                unknown_ozon_types=[],
            ))

    # CPC/PER_ORDER в transactions может быть БОЛЬШЕ чем в PA (доп. услуги, маркетинг)
    # — но не показываем дублирующие строки, оставляем общий итог. Юзер видит PA в основном.
    # Если разница > 5% — добавляем «прочие списания» от модели для прозрачности.
    def _residual(pa_sum: float, group: str, label_suffix: str) -> AdTypeRow | None:
        tx_sum = tx_groups.get(group, {}).get("spend", 0)
        diff = tx_sum - pa_sum
        if tx_sum > 0 and diff > tx_sum * 0.05:
            return AdTypeRow(
                type_key=f"tx-residual:{group}",
                label=f"Списания {group} (бух) − PA {label_suffix}",
                payment_model=group,
                source="transactions-only",
                spend=round(diff, 2), revenue=0, orders=0, drr_pct=None, daily=[],
                unknown_ozon_types=[],
            )
        return None

    extra_pc = _residual(pa_spend_pc, "PER_CLICK", "по клику")
    if extra_pc:
        rows_out.append(extra_pc)
    extra_po = _residual(pa_spend_po, "PER_ORDER", "за заказ")
    if extra_po:
        rows_out.append(extra_po)

    rows_out.sort(key=lambda x: x.spend, reverse=True)

    total_pa = sum(b["spend"] for b in pa_by_type.values())
    total_tx = sum(tx_by_op.values())
    note = (
        "SKU и search_promo: дневные данные Performance API. "
        "Баннеры/брендовая полка/бейджи: только суммарно из транзакций — "
        "Ozon не отдаёт дневную разбивку для этих типов."
    )

    return AdByTypeResp(
        period_from=date_from.isoformat(),
        period_to=date_to.isoformat(),
        rows=rows_out,
        total_spend_pa=round(total_pa, 2),
        total_spend_tx=round(total_tx, 2),
        note=note,
    )


# === Sankey: Воронка влияний =============================================

class SankeyNode(BaseModel):
    name: str


class SankeyLink(BaseModel):
    source: int
    target: int
    value: int


class SankeyResp(BaseModel):
    period_from: str
    period_to: str
    nodes: list[SankeyNode]
    links: list[SankeyLink]


@router.get("/sankey", response_model=SankeyResp)
async def funnel_sankey(
    days: int = Query(28, ge=1, le=365),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    product_id: str | None = Query(None),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SankeyResp:
    today = datetime.now(UTC).date()
    if not date_to:
        date_to = today
    if not date_from:
        date_from = date_to - timedelta(days=days)

    accs = await _account_ids(db, company_id=current_user.company_id, cabinet_ids=cabinet_ids)
    nodes = [
        SankeyNode(name="Показы"), SankeyNode(name="Клики"),
        SankeyNode(name="Корзина"), SankeyNode(name="Заказы"),
        SankeyNode(name="Доставлено"),
    ]
    if not accs:
        return SankeyResp(period_from=date_from.isoformat(), period_to=date_to.isoformat(),
                          nodes=nodes, links=[])

    pid: uuid.UUID | None = None
    if product_id:
        try:
            pid = uuid.UUID(product_id)
        except ValueError:
            pass

    row = await _aggregate(db, accs=accs, product_id=pid, date_from=date_from, date_to=date_to)
    imp = int(row.imp or 0)
    clicks = int(row.clicks or 0)
    cart = int(row.cart or 0)
    orders = int(row.orders or 0)
    deliv = int(row.deliv or 0)

    # каждое следующее значение ограничиваем предыдущим (граф не идёт назад)
    clicks = min(clicks, imp)
    cart = min(cart, clicks if clicks else imp)
    orders = min(orders, cart if cart else clicks)
    deliv = min(deliv, orders if orders else cart)

    links = [
        SankeyLink(source=0, target=1, value=clicks),
        SankeyLink(source=1, target=2, value=cart),
        SankeyLink(source=2, target=3, value=orders),
        SankeyLink(source=3, target=4, value=deliv),
    ]
    return SankeyResp(period_from=date_from.isoformat(), period_to=date_to.isoformat(),
                      nodes=nodes, links=links)
