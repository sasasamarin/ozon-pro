"""
Funnel v2 — 5 шагов + рекламная колонка + ДРР + drill-down + comparison.
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select, text
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
    """ВОРОНКА КАК В КАБИНЕТЕ OZON (6 шагов, без выдуманных «кликов»).

    Терминология (соответствует Ozon admin → Аналитика → Воронка продаж):
      1. impressions       = Показы всего (search + pdp)
      2. impressions_search= Показы в поиске и каталоге
      3. card_visits       = Посещения карточки товара (session_view_pdp)
      4. to_cart           = Добавления в корзину
      5. orders            = Заказано
      6. delivered         = Выкуплено
    Конверсии: search→card, card→cart, cart→order, order→delivery, overall.
    """
    impressions: int
    impressions_search: int
    card_visits: int           # = session_view_pdp; раньше было ошибочно «clicks»
    to_cart: int
    orders: int
    delivered: int
    revenue: float
    # Конверсии (% между шагами)
    search_to_card_pct: float | None   # Конверсия поиск→карточка (Ozon: ~22%)
    card_to_cart_pct: float | None     # Конверсия карточка→корзина (Ozon: ~9%)
    cart_conv_pct: float | None        # legacy: показы→корзина
    order_conv_pct: float | None       # корзина→заказ (Ozon: ~35%)
    delivery_conv_pct: float | None    # заказ→выкуп (Ozon: ~90%)
    overall_conv_pct: float | None     # показы→доставлено
    # Legacy поля (для обратной совместимости фронта, скоро удалю)
    clicks: int = 0
    ctr_pct: float | None = None
    click_to_cart_pct: float | None = None


class AdBreakdownRow(BaseModel):
    op_type: str
    label: str
    amount: float
    pct_of_total: float
    model: str  # CPC / CPA / FIXED


class AdBlock(BaseModel):
    total_spend: float
    drr_pct: float | None       # legacy = drr_overall_pct (для обратной совмест.)
    # ДРР разделён, юзер: «Ozon ДРР 1.1% (рекламный) vs наш 2.94% (общий)»
    drr_advertising_pct: float | None  # spend(PA) / revenue_from_ads(PA) — как у Ozon
    drr_overall_pct: float | None      # spend(tx) / total_revenue (доля в обороте)
    ad_revenue: float           # выручка ИЗ рекламы (ad_statistics.revenue)
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
    # Средняя «цена покупателя с СПП» за день — драйвер спроса, не влияет на выручку
    avg_customer_price: float | None = None
    avg_seller_price: float | None = None


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
    imp_search = int(row.imp_search or 0)
    card_visits = int(row.card_visits or 0)
    cart = int(row.cart or 0)
    orders = int(row.orders or 0)
    deliv = int(row.deliv or 0)
    return FunnelKPI(
        impressions=imp,
        impressions_search=imp_search,
        card_visits=card_visits,
        to_cart=cart, orders=orders, delivered=deliv,
        revenue=float(row.revenue or 0),
        search_to_card_pct=_safe_pct(card_visits, imp_search),
        card_to_cart_pct=_safe_pct(cart, card_visits),
        cart_conv_pct=_safe_pct(cart, imp),
        order_conv_pct=_safe_pct(orders, cart),
        delivery_conv_pct=_safe_pct(deliv, orders),
        overall_conv_pct=_safe_pct(deliv, imp),
        # legacy:
        clicks=card_visits,
        ctr_pct=_safe_pct(card_visits, imp),
        click_to_cart_pct=_safe_pct(cart, card_visits),
    )


def _parse_product_ids(
    product_id: str | None, product_ids: list[str] | None
) -> list[uuid.UUID]:
    """Принимаем обе формы (legacy product_id и новый product_ids)."""
    raw: list[str] = []
    if product_ids:
        raw.extend(product_ids)
    if product_id:
        raw.append(product_id)
    out: list[uuid.UUID] = []
    for s in raw:
        try:
            u = uuid.UUID(s)
            if u not in out:
                out.append(u)
        except (ValueError, AttributeError):
            pass
    return out


async def _aggregate(
    db: AsyncSession,
    *,
    accs: list[uuid.UUID],
    product_ids: list[uuid.UUID],
    date_from: date_cls,
    date_to: date_cls,
):
    where = [
        Product.ozon_account_id.in_(accs),
        AnalyticsDaily.date >= date_from,
        AnalyticsDaily.date <= date_to,
    ]
    if product_ids:
        where.append(AnalyticsDaily.product_id.in_(product_ids))
    q = select(
        # Показы всего = общая метрика Ozon hits_view (≈4× от search+pdp, совпадает
        # с кабинетом). Fallback на search+pdp для строк до ре-синка (hits_view IS NULL).
        func.coalesce(func.sum(func.coalesce(
            AnalyticsDaily.hits_view,
            AnalyticsDaily.hits_view_search + AnalyticsDaily.hits_view_pdp,
        )), 0).label("imp"),
        # Показы в поиске и каталоге (для конверсии «поиск→карточка»)
        func.coalesce(func.sum(AnalyticsDaily.hits_view_search), 0).label("imp_search"),
        # Посещения карточки = session_view_pdp (как в кабинете Ozon).
        # Раньше считалось как "клики" + session_view_search, давало CTR 86%.
        func.coalesce(func.sum(AnalyticsDaily.session_view_pdp), 0).label("card_visits"),
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
        return AdBlock(
            total_spend=0, drr_pct=None,
            drr_advertising_pct=None, drr_overall_pct=None, ad_revenue=0,
            breakdown=[], has_data=False,
        )
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

    drr_overall = (total / revenue * 100) if revenue else None

    # Рекламный ДРР как у Ozon: spend / revenue ТОЛЬКО от рекламы.
    # Источник = ad_statistics (PA daily), он покрывает SKU+search_promo.
    ad_pa_row = (await db.execute(
        select(
            func.coalesce(func.sum(AdStatistics.spend), 0).label("spend"),
            func.coalesce(func.sum(AdStatistics.revenue), 0).label("rev"),
        ).where(
            AdStatistics.ozon_account_id.in_(accs),
            AdStatistics.date >= date_from,
            AdStatistics.date <= date_to,
        )
    )).one()
    pa_spend = float(ad_pa_row.spend or 0)
    pa_rev = float(ad_pa_row.rev or 0)
    drr_ad = (pa_spend / pa_rev * 100) if pa_rev else None

    return AdBlock(
        total_spend=round(total, 2),
        drr_pct=round(drr_overall, 2) if drr_overall is not None else None,
        drr_advertising_pct=round(drr_ad, 2) if drr_ad is not None else None,
        drr_overall_pct=round(drr_overall, 2) if drr_overall is not None else None,
        ad_revenue=round(pa_rev, 2),
        breakdown=breakdown,
        has_data=total > 0,
    )


@router.get("/", response_model=FunnelV2Resp)
async def get_funnel_v2(
    days: int = Query(30, ge=1, le=730),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    product_id: str | None = Query(None),
    product_ids: list[str] | None = Query(None),
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

    pids = _parse_product_ids(product_id, product_ids)
    prod_name: str | None = None
    if pids:
        rows = (await db.execute(select(Product.name).where(Product.id.in_(pids)))).all()
        names = [r[0] for r in rows]
        if len(names) == 1:
            prod_name = names[0]
        elif len(names) > 1:
            prod_name = f"{names[0]} +{len(names) - 1}"

    if not accs:
        empty_kpi = FunnelKPI(
            impressions=0, clicks=0, to_cart=0, orders=0, delivered=0, revenue=0,
            cart_conv_pct=None, order_conv_pct=None,
            delivery_conv_pct=None, overall_conv_pct=None,
            ctr_pct=None, click_to_cart_pct=None,
        )
        empty_ad = AdBlock(
            total_spend=0, drr_pct=None,
            drr_advertising_pct=None, drr_overall_pct=None, ad_revenue=0,
            breakdown=[], has_data=False,
        )
        return FunnelV2Resp(
            period_from=date_from.isoformat(), period_to=date_to.isoformat(),
            product_id=product_id, product_name=prod_name,
            has_data=False, kpi=empty_kpi, prev_kpi=None, ad=empty_ad,
        )

    row = await _aggregate(db, accs=accs, product_ids=pids, date_from=date_from, date_to=date_to)
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
        prev_row = await _aggregate(db, accs=accs, product_ids=pids, date_from=prev_from, date_to=prev_to)
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
    product_ids: list[str] | None = Query(None),
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

    pids = _parse_product_ids(product_id, product_ids)

    where = [
        Product.ozon_account_id.in_(accs),
        AnalyticsDaily.date >= date_from,
        AnalyticsDaily.date <= date_to,
    ]
    if pids:
        where.append(AnalyticsDaily.product_id.in_(pids))

    rows = (await db.execute(
        select(
            AnalyticsDaily.date.label("d"),
            # Показы всего = hits_view (с fallback на search+pdp до ре-синка)
            func.coalesce(func.sum(func.coalesce(
                AnalyticsDaily.hits_view,
                AnalyticsDaily.hits_view_search + AnalyticsDaily.hits_view_pdp,
            )), 0).label("imp_total"),
            func.coalesce(func.sum(AnalyticsDaily.hits_view_search), 0).label("imp_s"),
            func.coalesce(func.sum(AnalyticsDaily.hits_view_pdp), 0).label("imp_p"),
            # «Посещения карточки» = session_view_pdp (как в кабинете Ozon).
            # Раньше было session_view_search+pdp — давало CTR 86%, юзер: «абсурд».
            func.coalesce(func.sum(AnalyticsDaily.session_view_pdp), 0).label("clicks"),
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

    # Параллельно — средние customer_price/seller_price по дням из order_items
    # (по тем же accounts/products/период). Это драйвер спроса для overlay на графике.
    price_where_sql = "o.ozon_account_id = ANY(:accs) AND DATE(o.order_created_at) BETWEEN :df AND :dt"
    price_params: dict = {"accs": list(map(str, accs)), "df": date_from, "dt": date_to}
    if pids:
        price_where_sql += " AND oi.product_id = ANY(:pids)"
        price_params["pids"] = list(map(str, pids))
    price_rows = (await db.execute(text(f"""
        SELECT DATE(o.order_created_at) d,
               AVG(oi.customer_price)::float avg_cust,
               AVG(oi.price)::float avg_sell
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE {price_where_sql}
          AND o.status = 'delivered'
          AND oi.price > 0
        GROUP BY 1
    """), price_params)).all()
    price_map = {pr.d: (pr.avg_cust, pr.avg_sell) for pr in price_rows}

    out: list[FunnelDailyPoint] = []
    for r in rows:
        imp_s = int(r.imp_s or 0)
        imp_p = int(r.imp_p or 0)
        imp = int(r.imp_total or 0)  # «Показы всего» = hits_view (Ozon UI), не search+pdp
        clicks = int(r.clicks or 0)
        cart_s = int(r.cart_s or 0)
        cart_p = int(r.cart_p or 0)
        cart = cart_s + cart_p
        orders = int(r.orders or 0)
        deliv = int(r.deliv or 0)
        avg_cust, avg_sell = price_map.get(r.d, (None, None))
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
            avg_customer_price=float(avg_cust) if avg_cust else None,
            avg_seller_price=float(avg_sell) if avg_sell else None,
        ))
    return out


@router.get("/best-worst-days", response_model=dict)
async def best_worst_days(
    days: int = Query(90, ge=7, le=365),
    metric: str = Query("order", description="overall|cart|order|delivery"),
    product_id: str | None = Query(None),
    product_ids: list[str] | None = Query(None),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    today = datetime.now(UTC).date()
    date_from = today - timedelta(days=days)

    label_map = {
        "cart":     ("Показы",  "В корзину"),
        "order":    ("Показы", "Заказы"),
        "delivery": ("Заказы",  "Доставлено"),
        "overall":  ("Показы",  "Доставлено"),
    }
    from_label, to_label = label_map.get(metric, label_map["order"])

    accs = await _account_ids(db, company_id=current_user.company_id, cabinet_ids=cabinet_ids)
    if not accs:
        return {"best": [], "worst": [], "metric": metric, "from_label": from_label, "to_label": to_label}

    pids = _parse_product_ids(product_id, product_ids)

    where = [
        Product.ozon_account_id.in_(accs),
        AnalyticsDaily.date >= date_from,
    ]
    if pids:
        where.append(AnalyticsDaily.product_id.in_(pids))

    rows = (await db.execute(
        select(
            AnalyticsDaily.date.label("d"),
            func.coalesce(func.sum(func.coalesce(
                AnalyticsDaily.hits_view,
                AnalyticsDaily.hits_view_search + AnalyticsDaily.hits_view_pdp,
            )), 0).label("imp"),
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
            # Показ → Заказ (день в день): юзер просила это как дефолт (не доставку,
            # т.к. доставка может прийти через месяц после показа → искажение).
            if imp < 100:
                return None
            return BestWorstDay(date=r.d.isoformat(), from_value=imp, to_value=orders,
                                conv_pct=_safe_pct(orders, imp) or 0, revenue=revenue)
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

    # «Средний день» = медиана конверсии за период (юзер: «нужна норма»).
    average = None
    if items:
        sorted_items = sorted(items, key=lambda x: x.conv_pct)
        median_item = sorted_items[len(sorted_items) // 2]
        avg_conv = sum(x.conv_pct for x in items) / len(items)
        avg_from = sum(x.from_value for x in items) / len(items)
        avg_to = sum(x.to_value for x in items) / len(items)
        avg_rev = sum(x.revenue for x in items) / len(items)
        average = {
            "date": f"средний из {len(items)} дн",
            "from_value": int(avg_from),
            "to_value": int(avg_to),
            "conv_pct": round(avg_conv, 2),
            "median_pct": round(median_item.conv_pct, 2),
            "revenue": round(avg_rev, 2),
            "days_count": len(items),
        }

    return {
        "best": [b.dict() for b in best],
        "worst": [w.dict() for w in worst],
        "average": average,
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
    # === Цены ===
    price: float | None = None              # current_price (= 33000, зачёркнутая «до скидки»)
    marketing_price: float | None = None    # marketing_seller_price (= 19958, цена продавца)
    customer_price: float | None = None     # средняя «оплачено покупателем» с СПП (= 11000)
    # === Прочие drivers ===
    ad_spend: float | None = None           # расход на рекламу за этот день
    stock_total: int | None = None          # остаток на конец дня (для per-product)
    is_stockout: bool = False               # был ли товар в стокауте


class LagCorr(BaseModel):
    lag_days: int
    r: float | None


class AnomalyPoint(BaseModel):
    date: str
    impressions: int
    orders: int
    reason: str          # человеческая причина: "стокаут", "цена выросла на 12%" и т.д.
    severity: str        # "high" | "medium" | "low"


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
    anomalies: list[AnomalyPoint] = []
    has_price_overlay: bool = False         # есть ли реальная цена/СПП по дням
    product_name: str | None = None


@router.get("/correlations", response_model=CorrelationsResp)
async def funnel_correlations(
    days: int = Query(28, ge=14, le=365),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    product_id: str | None = Query(None),
    product_ids: list[str] | None = Query(None),
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

    pids = _parse_product_ids(product_id, product_ids)
    pid = pids[0] if len(pids) == 1 else None  # overlay цены/СПП только для одиночного

    where = [
        Product.ozon_account_id.in_(accs),
        AnalyticsDaily.date >= date_from,
        AnalyticsDaily.date <= date_to,
    ]
    if pids:
        where.append(AnalyticsDaily.product_id.in_(pids))

    rows = (await db.execute(
        select(
            AnalyticsDaily.date.label("d"),
            func.coalesce(func.sum(func.coalesce(
                AnalyticsDaily.hits_view,
                AnalyticsDaily.hits_view_search + AnalyticsDaily.hits_view_pdp,
            )), 0).label("imp"),
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

    # ===== Оверлеи цены/СПП/стокаута (только когда product_id задан)
    product_name: str | None = None
    has_price_overlay = False
    if pid:
        prod = (await db.execute(select(Product).where(Product.id == pid))).scalar_one_or_none()
        if prod:
            product_name = prod.name
            cur_price = float(prod.current_price) if prod.current_price is not None else None
            mk_price = float(prod.marketing_price) if prod.marketing_price is not None else None
            if cur_price or mk_price:
                has_price_overlay = True
                for p in series:
                    p.price = cur_price
                    p.marketing_price = mk_price

            # Остаток per day — последний снапшот ≤ конец дня.
            # ВАЖНО: stocks содержит разные warehouse_type (AGG, FBO, FBS, FBO_WH).
            # Тупой SUM удваивает (вид 28.05: AGG=534 + FBO=9070 = 9634, факт 534).
            # Берём логику /products: приоритет FBO_WH per-warehouse, fallback AGG.
            stk_rows = (await db.execute(text("""
              WITH per_day AS (
                SELECT date_trunc('day', time)::date d,
                       warehouse_type,
                       MAX(time) last_t
                FROM stocks
                WHERE product_id = :pid AND time >= :dfrom AND time < :dto
                GROUP BY 1, warehouse_type
              ),
              priority_type AS (
                SELECT d,
                       CASE
                         WHEN bool_or(warehouse_type='FBO_WH') THEN 'FBO_WH'
                         WHEN bool_or(warehouse_type='AGG')    THEN 'AGG'
                         WHEN bool_or(warehouse_type='FBO')    THEN 'FBO'
                         ELSE 'FBS'
                       END AS chosen_type
                FROM per_day GROUP BY d
              )
              SELECT s.time::date d,
                     SUM(GREATEST(s.free_to_sell - s.reserved, 0)) free
              FROM stocks s
              JOIN per_day pd ON pd.d = s.time::date AND pd.warehouse_type = s.warehouse_type AND pd.last_t = s.time
              JOIN priority_type pt ON pt.d = s.time::date AND pt.chosen_type = s.warehouse_type
              WHERE s.product_id = :pid
              GROUP BY s.time::date
            """), {
                "pid": str(pid),
                "dfrom": datetime.combine(date_from, datetime.min.time(), tzinfo=UTC),
                "dto": datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=UTC),
            })).all()
            stock_by_day = {r.d.isoformat(): int(r.free or 0) for r in stk_rows}
            last_known = None
            for p in series:
                if p.date in stock_by_day:
                    last_known = stock_by_day[p.date]
                p.is_stockout = (last_known == 0) if last_known is not None else False

            # avg customer_price (СПП) по дням из order_items — динамический оверлей
            cp_rows = (await db.execute(text("""
              SELECT DATE(o.order_created_at) d, AVG(oi.customer_price)::float avg_cp
              FROM order_items oi JOIN orders o ON o.id = oi.order_id
              WHERE oi.product_id = :pid AND o.status = 'delivered'
                AND DATE(o.order_created_at) BETWEEN :df AND :dt
                AND oi.customer_price IS NOT NULL
              GROUP BY 1
            """), {"pid": str(pid), "df": date_from, "dt": date_to})).all()
            cp_by_day = {r.d.isoformat(): float(r.avg_cp) for r in cp_rows if r.avg_cp}
            for p in series:
                if p.date in cp_by_day:
                    p.customer_price = cp_by_day[p.date]
                    has_price_overlay = True

            # Остаток на конец каждого дня (для overlay)
            stock_total_by_day = {r.d.isoformat(): int(r.free or 0) for r in stk_rows}
            last_stock = None
            for p in series:
                if p.date in stock_total_by_day:
                    last_stock = stock_total_by_day[p.date]
                p.stock_total = last_stock

    # ad_spend по дням (для overlay) — для всех товаров или одного
    ad_where = [
        AdStatistics.ozon_account_id.in_(accs),
        AdStatistics.date >= date_from,
        AdStatistics.date <= date_to,
    ]
    if pids:
        ad_where.append(AdStatistics.product_id.in_(pids))
    ad_rows = (await db.execute(
        select(
            AdStatistics.date.label("d"),
            func.coalesce(func.sum(AdStatistics.spend), 0).label("spend"),
        ).where(*ad_where).group_by(AdStatistics.date)
    )).all()
    ad_spend_by_day = {r.d.isoformat(): float(r.spend or 0) for r in ad_rows}
    for p in series:
        if p.date in ad_spend_by_day:
            p.ad_spend = ad_spend_by_day[p.date]

    imps = [float(p.impressions) for p in series]
    ords = [float(p.orders) for p in series]
    r0 = _pearson(imps, ords)
    beta = _log_elasticity(imps, ords)

    # Лаг-корреляция: импрессии (i) ↔ заказы (i+lag). Если лаг=1 — заказы завтра.
    # Best_lag: МИНИМАЛЬНЫЙ лаг с r ≥ 70% от лучшего положительного r.
    # Юзер: если r(0)=0.37 (макс среди положительных), а r(10)=0.42 — это
    # шум на коротком ряду, не "эффект через 10 дней". Берём наименьший лаг
    # где сила связи близка к максимальной — это самое честное соответствие.
    lag_steps = [0, 1, 2, 3, 5, 7, 10, 14]
    lags: list[LagCorr] = []
    lag_values: list[tuple[int, float]] = []  # только положительные r ≥ 0.3
    for lag in lag_steps:
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
        if r_lag is not None and r_lag >= 0.3:
            lag_values.append((lag, r_lag))

    if lag_values:
        max_r = max(v for _, v in lag_values)
        # Берём минимальный лаг где r ≥ 70% от максимума (приоритет малых лагов)
        candidates = [lag for lag, v in lag_values if v >= max_r * 0.7]
        best_lag: int | None = min(candidates) if candidates else None
    else:
        best_lag = None

    headline = _strength_label_ru(r0)
    if not imps or not ords or len(imps) < 3:
        explanation = "Недостаточно дней для расчёта (нужно ≥3)."
    else:
        parts: list[str] = []
        if r0 is not None:
            parts.append(f"Коэффициент Пирсона r = {r0:.2f}")
        if beta is not None and beta > 0:
            parts.append(f"эластичность β = {beta:.2f} (рост показов на 10% → заказы +{beta * 10:.1f}%)")
        elif beta is not None and beta < 0:
            parts.append(f"эластичность β = {beta:.2f} (обратная зависимость)")
        if best_lag is not None and best_lag == 0:
            parts.append("эффект в тот же день")
        elif best_lag is not None and best_lag > 0:
            parts.append(f"эффект сильнее всего проявляется через {best_lag} дн.")
        explanation = "; ".join(parts) + "."

    # ===== Аномалии: "много показов, мало заказов" + причина
    anomalies: list[AnomalyPoint] = []
    if len(series) >= 7:
        # baseline по медиане (устойчиво к выбросам)
        sorted_imps = sorted(imps)
        sorted_ords = sorted(ords)
        med_imp = sorted_imps[len(sorted_imps) // 2] or 1
        med_ord = sorted_ords[len(sorted_ords) // 2] or 1

        for p in series:
            imp_ratio = (p.impressions / med_imp) if med_imp else 1.0
            ord_ratio = (p.orders / med_ord) if med_ord else 1.0

            # «много показов, мало заказов»: показы ≥ 120%, заказы ≤ 70%
            if imp_ratio >= 1.2 and ord_ratio <= 0.7:
                reasons: list[str] = []
                if p.is_stockout:
                    reasons.append("товар в стокауте 0 шт")
                # Цена выше типичной: если marketing_price задана как константа,
                # история цены пока сравнивается только при наличии. Для MVP
                # отмечаем «возможна смена цены/СПП».
                if p.marketing_price and p.price and p.marketing_price < p.price * 0.85:
                    reasons.append(f"СПП {p.marketing_price:.0f}₽ значительно ниже базы {p.price:.0f}₽")
                if not reasons:
                    reasons.append("конверсия карточки упала — проверьте отзывы/контент/CTR")
                anomalies.append(AnomalyPoint(
                    date=p.date,
                    impressions=p.impressions,
                    orders=p.orders,
                    reason=" / ".join(reasons),
                    severity="high" if ord_ratio <= 0.4 else "medium",
                ))

    return CorrelationsResp(
        period_from=date_from.isoformat(),
        period_to=date_to.isoformat(),
        series=series,
        r=round(r0, 4) if r0 is not None else None,
        elasticity=round(beta, 4) if beta is not None else None,
        lags=lags,
        best_lag_days=best_lag,
        headline=headline,
        explanation=explanation,
        anomalies=anomalies,
        has_price_overlay=has_price_overlay,
        product_name=product_name,
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
    impressions: int        # показы рекламы (PA only)
    clicks: int             # клики/переходы из рекламы (PA only)
    ctr_pct: float | None   # clicks/impressions × 100
    cpc: float | None       # spend / clicks
    cpa: float | None       # spend / orders
    romi_pct: float | None  # (revenue - spend) / spend × 100
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

    # === PA daily через ad_statistics ↔ ad_campaigns (+ показы и клики)
    pa_rows = (await db.execute(
        select(
            AdCampaign.campaign_type.label("ct"),
            AdStatistics.date.label("d"),
            func.coalesce(func.sum(AdStatistics.spend), 0).label("spend"),
            func.coalesce(func.sum(AdStatistics.revenue), 0).label("rev"),
            func.coalesce(func.sum(AdStatistics.orders), 0).label("ord"),
            func.coalesce(func.sum(AdStatistics.impressions), 0).label("imp"),
            func.coalesce(func.sum(AdStatistics.clicks), 0).label("clk"),
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
            "spend": 0.0, "rev": 0.0, "ord": 0, "imp": 0, "clk": 0, "daily": []
        })
        spend_d = float(r.spend or 0)
        rev_d = float(r.rev or 0)
        ord_d = int(r.ord or 0)
        imp_d = int(r.imp or 0)
        clk_d = int(r.clk or 0)
        bucket["spend"] += spend_d
        bucket["rev"] += rev_d
        bucket["ord"] += ord_d
        bucket["imp"] += imp_d
        bucket["clk"] += clk_d
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

    def _mk_metrics(spend: float, revenue: float, orders: int, imp: int, clk: int):
        drr = (spend / revenue * 100) if revenue else None
        ctr = (clk / imp * 100) if imp else None
        cpc = (spend / clk) if clk else None
        cpa = (spend / orders) if orders else None
        romi = ((revenue - spend) / spend * 100) if spend else None
        return (
            round(drr, 2) if drr is not None else None,
            round(ctr, 2) if ctr is not None else None,
            round(cpc, 2) if cpc is not None else None,
            round(cpa, 2) if cpa is not None else None,
            round(romi, 1) if romi is not None else None,
        )

    # PA-rows: dump as-is per campaign_type
    for ct, b in pa_by_type.items():
        label, pay = _CAMPAIGN_TYPE_LABEL.get(ct, (ct, "?"))
        drr, ctr, cpc, cpa, romi = _mk_metrics(
            b["spend"], b["rev"], b["ord"], b["imp"], b["clk"]
        )
        rows_out.append(AdTypeRow(
            type_key=ct, label=label, payment_model=pay,
            source="PA-daily",
            spend=round(b["spend"], 2), revenue=round(b["rev"], 2), orders=b["ord"],
            impressions=b["imp"], clicks=b["clk"],
            ctr_pct=ctr, cpc=cpc, cpa=cpa, romi_pct=romi,
            drr_pct=drr,
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
                spend=round(sp, 2), revenue=0, orders=0,
                impressions=0, clicks=0,
                ctr_pct=None, cpc=None, cpa=None, romi_pct=None,
                drr_pct=None, daily=[],
                unknown_ozon_types=[],
            ))

    def _residual(pa_sum: float, group: str, label_suffix: str) -> AdTypeRow | None:
        tx_sum = tx_groups.get(group, {}).get("spend", 0)
        diff = tx_sum - pa_sum
        if tx_sum > 0 and diff > tx_sum * 0.05:
            return AdTypeRow(
                type_key=f"tx-residual:{group}",
                label=f"Списания {group} (бух) − PA {label_suffix}",
                payment_model=group,
                source="transactions-only",
                spend=round(diff, 2), revenue=0, orders=0,
                impressions=0, clicks=0,
                ctr_pct=None, cpc=None, cpa=None, romi_pct=None,
                drr_pct=None, daily=[],
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
    conv_pct: float | None     # конверсия source→target, %
    label: str                  # подпись: "CTR 86.9%"
    is_bottleneck: bool         # узкое горлышко (наименьшая конверсия)


class SankeyResp(BaseModel):
    period_from: str
    period_to: str
    nodes: list[SankeyNode]
    links: list[SankeyLink]
    bottleneck_step: str | None  # имя ноды-горлышка


@router.get("/sankey", response_model=SankeyResp)
async def funnel_sankey(
    days: int = Query(28, ge=1, le=365),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    product_id: str | None = Query(None),
    product_ids: list[str] | None = Query(None),
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
    # 5 основных узлов + 4 drop-узла («Ушли»). Без drop-узлов recharts равняет
    # узел источника к величине единственного outflow, и Показы визуально =
    # Клики (юзер: «Показы 5945 = Клики 5945, невозможно при CTR 9.92%»).
    nodes = [
        SankeyNode(name="Показы"),       # 0
        SankeyNode(name="Клики"),        # 1
        SankeyNode(name="Корзина"),      # 2
        SankeyNode(name="Заказы"),       # 3
        SankeyNode(name="Доставлено"),   # 4
        SankeyNode(name="Ушли без клика"),       # 5
        SankeyNode(name="Не добавили в корзину"),# 6
        SankeyNode(name="Бросили корзину"),      # 7
        SankeyNode(name="Не дошли"),             # 8
    ]
    if not accs:
        return SankeyResp(period_from=date_from.isoformat(), period_to=date_to.isoformat(),
                          nodes=nodes, links=[])

    pids = _parse_product_ids(product_id, product_ids)
    row = await _aggregate(db, accs=accs, product_ids=pids, date_from=date_from, date_to=date_to)
    imp = int(row.imp or 0)
    clicks = int(row.card_visits or 0)
    cart = int(row.cart or 0)
    orders = int(row.orders or 0)
    deliv = int(row.deliv or 0)

    # каждое следующее значение ограничиваем предыдущим (граф не идёт назад)
    clicks = min(clicks, imp)
    cart = min(cart, clicks if clicks else imp)
    orders = min(orders, cart if cart else clicks)
    deliv = min(deliv, orders if orders else cart)

    # Основные «успешные» переходы — толщина = passed_to_next
    # + drop-link «осталось» — толщина = source - passed, чтобы recharts корректно
    # отрисовал узел источника во всю его величину.
    main_steps = [
        # (src_idx, src_value, tgt_idx, tgt_value, drop_idx, metric_label)
        (0, imp,    1, clicks, 5, "CTR"),
        (1, clicks, 2, cart,   6, "% в корзину"),
        (2, cart,   3, orders, 7, "% в заказ"),
        (3, orders, 4, deliv,  8, "выкуп"),
    ]
    raw_main: list[dict] = []
    for src_idx, src_v, tgt_idx, tgt_v, drop_idx, metric_name in main_steps:
        conv = (tgt_v / src_v * 100) if src_v else None
        raw_main.append({
            "src_idx": src_idx, "tgt_idx": tgt_idx, "drop_idx": drop_idx,
            "src_v": src_v, "tgt_v": tgt_v,
            "conv": conv, "metric": metric_name,
        })

    # Узкое горлышко — переход с минимальной конверсией (но > 0)
    valid = [(i, l["conv"]) for i, l in enumerate(raw_main) if l["conv"] and l["conv"] > 0]
    bottleneck_idx = min(valid, key=lambda x: x[1])[0] if valid else None
    bottleneck_step = (
        f"{nodes[raw_main[bottleneck_idx]['src_idx']].name} → {nodes[raw_main[bottleneck_idx]['tgt_idx']].name}"
        if bottleneck_idx is not None else None
    )

    links: list[SankeyLink] = []
    for i, l in enumerate(raw_main):
        pct_str = f"{l['conv']:.2f}%" if l['conv'] is not None else "—"
        # Основной поток: src → tgt со значением tgt_v (= сколько прошло)
        links.append(SankeyLink(
            source=l["src_idx"], target=l["tgt_idx"], value=max(l["tgt_v"], 0),
            conv_pct=round(l["conv"], 2) if l["conv"] is not None else None,
            label=f"{l['metric']} {pct_str}",
            is_bottleneck=(i == bottleneck_idx),
        ))
        # Drop-поток: src → «Ушли» со значением (src_v - tgt_v)
        dropped = max(l["src_v"] - l["tgt_v"], 0)
        if dropped > 0:
            links.append(SankeyLink(
                source=l["src_idx"], target=l["drop_idx"], value=dropped,
                conv_pct=None,
                label=f"ушло {dropped:,}".replace(",", " "),
                is_bottleneck=False,
            ))

    return SankeyResp(period_from=date_from.isoformat(), period_to=date_to.isoformat(),
                      nodes=nodes, links=links, bottleneck_step=bottleneck_step)
