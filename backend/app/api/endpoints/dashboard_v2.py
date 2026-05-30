"""
Dashboard v2 — Power BI стиль: custom-period + granularity + comparison + clusters.

GET /api/v1/dashboard/v2
  ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
  &granularity=day|week|month
  &compare=none|prev_period|year_ago
  &cabinet_ids=<uuid>...
  &with_vat=true|false
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
from app.models import Order, OrderItem, OzonAccount, Product, Transaction, User

router = APIRouter()
UTC = timezone.utc


# === Schemas =================================================================


class KPIBlock(BaseModel):
    # «Заказано» — все заказы периода (как в кабинете Ozon «Заказано на сумму»)
    ordered_revenue: float
    ordered_count: int
    ordered_change_pct: float | None
    # «Продажи / Доставлено» — только status=delivered
    revenue: float                  # = delivered_revenue (для обратной совместимости)
    revenue_change_pct: float | None
    delivered_count: int
    # Промежуточные статусы — разница между заказано и продажами
    in_transit_revenue: float       # delivering + awaiting_*
    cancelled_revenue: float
    cancelled_count: int

    gross_profit: float
    gross_profit_change_pct: float | None
    orders_count: int               # = delivered_count (legacy)
    orders_change_pct: float | None
    aov: float
    aov_change_pct: float | None
    ozon_expenses: float
    expense_share_pct: float | None
    sparkline: list[float]


class TimePoint(BaseModel):
    bucket: str            # ISO дата начала bucket'а
    revenue: float
    expenses: float
    cogs: float
    profit: float
    orders: int


class ExpenseSegment(BaseModel):
    category: str
    amount: float
    pct: float
    op_type_filter: str | None  # параметр для drill-down в /finance/transactions


class TopProduct(BaseModel):
    product_id: str
    name: str
    offer_id: str
    image_url: str | None
    revenue: float
    orders: int
    units: int
    margin: float | None       # gross_profit = revenue - cogs - commission (если cost+commission известны)
    margin_pct: float | None


class ClusterSegment(BaseModel):
    cluster: str               # cluster_from название склада-источника
    revenue: float
    orders: int
    pct: float


class DashboardV2Response(BaseModel):
    period_from: str
    period_to: str
    granularity: str
    compare: str
    has_missing_costs: bool
    missing_costs_count: int

    kpi: KPIBlock
    series: list[TimePoint]
    expense_breakdown: list[ExpenseSegment]
    top_products: list[TopProduct]
    clusters: list[ClusterSegment]


# === Helpers =================================================================


_EXPENSE_BUCKETS = [
    ("Комиссия Ozon", "sale_commission", "OperationAgentDeliveredToCustomer"),
    ("Логистика к клиенту", "delivery_to_customer", "OperationAgentDeliveredToCustomer"),
    ("Возвратная логистика", "return_logistics", "OperationItemReturn"),
    ("Last mile", "last_mile", "OperationAgentDeliveredToCustomer"),
    ("Хранение", "storage", None),
    ("Размещение", "placement", None),
    ("Эквайринг", "acquiring", "MarketplaceRedistributionOfAcquiringOperation"),
    ("Реклама", "advertising", "OperationMarketplaceCostPerClick"),
    ("Утилизация", "utilization", None),
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


def _resolve_compare_window(
    *, from_d: date_cls, to_d: date_cls, mode: str
) -> tuple[date_cls, date_cls] | None:
    if mode == "none":
        return None
    if mode == "year_ago":
        return (from_d - timedelta(days=365), to_d - timedelta(days=365))
    # prev_period — окно такой же длины перед текущим
    span = (to_d - from_d)
    return (from_d - span - timedelta(days=1), from_d - timedelta(days=1))


async def _kpi_for_window(
    db: AsyncSession,
    *,
    accs: list[uuid.UUID],
    dt_from: datetime,
    dt_to: datetime,
) -> dict:
    """Возвращает по окну: ordered/delivered/in_transit/cancelled + cogs + expenses.

    «Заказано» (как в Ozon кабинете) = SUM(Order.total_amount) по ВСЕМ статусам.
    «Продажи» (=delivered) = SUM где status=delivered.
    «В пути» = delivering + awaiting_*.
    «Отменено» = cancelled.
    """
    if not accs:
        return {
            "ordered_revenue": 0.0, "ordered_count": 0,
            "delivered_revenue": 0.0, "delivered_count": 0,
            "in_transit_revenue": 0.0, "cancelled_revenue": 0.0, "cancelled_count": 0,
            "cogs": 0.0, "ozon_expenses": 0.0,
        }

    rev_row = (await db.execute(
        select(
            func.coalesce(func.sum(Order.total_amount), 0).label("ordered_revenue"),
            func.count(Order.id).label("ordered_count"),
            func.coalesce(func.sum(
                func.case((Order.status == "delivered", Order.total_amount), else_=0)
            ), 0).label("delivered_revenue"),
            func.sum(
                func.case((Order.status == "delivered", 1), else_=0)
            ).label("delivered_count"),
            func.coalesce(func.sum(
                func.case((Order.status.in_(
                    ("delivering", "awaiting_packaging", "awaiting_deliver")
                ), Order.total_amount), else_=0)
            ), 0).label("in_transit_revenue"),
            func.coalesce(func.sum(
                func.case((Order.status == "cancelled", Order.total_amount), else_=0)
            ), 0).label("cancelled_revenue"),
            func.sum(
                func.case((Order.status == "cancelled", 1), else_=0)
            ).label("cancelled_count"),
        ).where(
            Order.ozon_account_id.in_(accs),
            Order.order_created_at >= dt_from,
            Order.order_created_at < dt_to,
        )
    )).one()

    # COGS считаем по доставленным (только delivered формирует факт. себестоимость)
    cogs_row = await db.execute(
        select(
            func.coalesce(
                func.sum(OrderItem.quantity * func.coalesce(Product.cost_price, 0)), 0
            )
        )
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            Order.ozon_account_id.in_(accs),
            Order.order_created_at >= dt_from,
            Order.order_created_at < dt_to,
            Order.status == "delivered",
        )
    )
    cogs = float(cogs_row.scalar() or 0)

    exp_cols = [
        func.coalesce(func.sum(func.abs(getattr(Transaction, f))), 0)
        for _, f, _ in _EXPENSE_BUCKETS
    ]
    exp_row = (await db.execute(
        select(*exp_cols).where(
            Transaction.ozon_account_id.in_(accs),
            Transaction.time >= dt_from,
            Transaction.time < dt_to,
        )
    )).one()
    ozon_expenses = sum(float(v or 0) for v in exp_row)

    return {
        "ordered_revenue": float(rev_row.ordered_revenue or 0),
        "ordered_count": int(rev_row.ordered_count or 0),
        "delivered_revenue": float(rev_row.delivered_revenue or 0),
        "delivered_count": int(rev_row.delivered_count or 0),
        "in_transit_revenue": float(rev_row.in_transit_revenue or 0),
        "cancelled_revenue": float(rev_row.cancelled_revenue or 0),
        "cancelled_count": int(rev_row.cancelled_count or 0),
        "cogs": cogs,
        "ozon_expenses": ozon_expenses,
    }


def _pct(curr: float, prev: float) -> float | None:
    if not prev:
        return None
    return round((curr - prev) / abs(prev) * 100, 1)


# === Endpoint ================================================================


@router.get("/", response_model=DashboardV2Response)
async def get_dashboard_v2(
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    days: int = Query(30, ge=1, le=730),
    granularity: str = Query("day", description="day | week | month"),
    compare: str = Query("prev_period", description="none | prev_period | year_ago"),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    top_limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardV2Response:
    today = datetime.now(UTC).date()
    if not date_to:
        date_to = today
    if not date_from:
        date_from = date_to - timedelta(days=days)

    dt_from = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
    dt_to = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=UTC)

    accs = await _account_ids(db, company_id=current_user.company_id, cabinet_ids=cabinet_ids)

    # ===== KPI текущий период =====
    k = await _kpi_for_window(db, accs=accs, dt_from=dt_from, dt_to=dt_to)
    revenue = k["delivered_revenue"]    # «продажи» (legacy revenue)
    orders = k["delivered_count"]
    cogs = k["cogs"]
    ozon_exp = k["ozon_expenses"]
    gross_profit = revenue - cogs - ozon_exp
    aov = revenue / orders if orders else 0
    expense_share = (ozon_exp / revenue * 100) if revenue else None

    # ===== Сравнение =====
    cmp = _resolve_compare_window(from_d=date_from, to_d=date_to, mode=compare)
    if cmp:
        cmp_from = datetime.combine(cmp[0], datetime.min.time(), tzinfo=UTC)
        cmp_to = datetime.combine(cmp[1] + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        pk = await _kpi_for_window(db, accs=accs, dt_from=cmp_from, dt_to=cmp_to)
        p_rev = pk["delivered_revenue"]
        p_ord = pk["delivered_count"]
        p_cogs = pk["cogs"]
        p_exp = pk["ozon_expenses"]
        p_ordered = pk["ordered_revenue"]
        p_gross = p_rev - p_cogs - p_exp
        p_aov = p_rev / p_ord if p_ord else 0
    else:
        p_rev = p_ord = p_gross = p_aov = p_ordered = 0

    # ===== Series по granularity =====
    trunc_unit = granularity if granularity in ("day", "week", "month") else "day"
    bucket = func.date_trunc(trunc_unit, Order.order_created_at).label("b")

    rev_series = (await db.execute(
        select(
            bucket,
            func.coalesce(func.sum(Order.total_amount), 0).label("revenue"),
            func.count(Order.id).label("orders"),
            func.coalesce(
                func.sum(OrderItem.quantity * func.coalesce(Product.cost_price, 0)), 0
            ).label("cogs"),
        )
        .select_from(Order)
        .outerjoin(OrderItem, OrderItem.order_id == Order.id)
        .outerjoin(Product, Product.id == OrderItem.product_id)
        .where(
            Order.ozon_account_id.in_(accs) if accs else False,
            Order.order_created_at >= dt_from,
            Order.order_created_at < dt_to,
            Order.status == "delivered",
        )
        .group_by("b")
        .order_by("b")
    )).all()

    exp_bucket = func.date_trunc(trunc_unit, Transaction.time).label("b")
    exp_series = (await db.execute(
        select(
            exp_bucket,
            func.coalesce(
                func.sum(
                    func.abs(Transaction.sale_commission)
                    + Transaction.delivery_to_customer + Transaction.return_logistics
                    + Transaction.last_mile + Transaction.storage + Transaction.placement
                    + Transaction.acquiring + Transaction.advertising + Transaction.utilization
                ),
                0,
            ).label("expenses"),
        )
        .where(
            Transaction.ozon_account_id.in_(accs) if accs else False,
            Transaction.time >= dt_from,
            Transaction.time < dt_to,
        )
        .group_by("b")
        .order_by("b")
    )).all()
    exp_by_bucket = {r.b.date().isoformat(): float(r.expenses or 0) for r in exp_series}

    series: list[TimePoint] = []
    sparkline: list[float] = []
    for r in rev_series:
        b_key = r.b.date().isoformat()
        rev = float(r.revenue or 0)
        cogs_b = float(r.cogs or 0)
        exp_b = exp_by_bucket.get(b_key, 0)
        profit = rev - cogs_b - exp_b
        series.append(TimePoint(
            bucket=b_key,
            revenue=round(rev, 2),
            expenses=round(exp_b, 2),
            cogs=round(cogs_b, 2),
            profit=round(profit, 2),
            orders=int(r.orders or 0),
        ))
        sparkline.append(rev)

    # ===== Expense breakdown =====
    if accs:
        cols = [
            (label, op_filter, func.coalesce(func.sum(func.abs(getattr(Transaction, f))), 0).label(f))
            for label, f, op_filter in _EXPENSE_BUCKETS
        ]
        sel = select(*[c[2] for c in cols]).where(
            Transaction.ozon_account_id.in_(accs),
            Transaction.time >= dt_from,
            Transaction.time < dt_to,
        )
        exp_row = (await db.execute(sel)).one()
        total_exp = sum(float(v or 0) for v in exp_row)
        expense_breakdown = []
        for i, (label, op_filter, _) in enumerate(cols):
            v = float(exp_row[i] or 0)
            if v > 0:
                expense_breakdown.append(ExpenseSegment(
                    category=label,
                    amount=round(v, 2),
                    pct=round(v / total_exp * 100, 1) if total_exp else 0,
                    op_type_filter=op_filter,
                ))
        expense_breakdown.sort(key=lambda x: x.amount, reverse=True)
    else:
        expense_breakdown = []

    # ===== Top products =====
    top_products: list[TopProduct] = []
    if accs:
        rows = (await db.execute(
            select(
                Product.id.label("pid"),
                Product.name.label("name"),
                Product.offer_id.label("offer_id"),
                Product.cost_price.label("cost_price"),
                func.coalesce(func.sum(OrderItem.total_price), 0).label("revenue"),
                func.coalesce(func.sum(OrderItem.quantity), 0).label("units"),
                func.coalesce(func.sum(OrderItem.commission), 0).label("commission"),
                func.count(func.distinct(Order.id)).label("orders"),
            )
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id)
            .where(
                Order.ozon_account_id.in_(accs),
                Order.order_created_at >= dt_from,
                Order.order_created_at < dt_to,
                Order.status == "delivered",
            )
            .group_by(Product.id, Product.name, Product.offer_id, Product.cost_price)
            .order_by(desc("revenue"))
            .limit(top_limit)
        )).all()

        # raw_data для image_url
        pids = [r.pid for r in rows]
        image_map: dict[uuid.UUID, str | None] = {}
        if pids:
            img_rows = await db.execute(
                select(Product.id, Product.raw_data).where(Product.id.in_(pids))
            )
            for pid, raw in img_rows.all():
                image_map[pid] = _extract_image(raw)

        for r in rows:
            rev = float(r.revenue or 0)
            cogs_v = (float(r.cost_price or 0) * int(r.units or 0)) if r.cost_price else 0
            comm = float(r.commission or 0)
            margin = rev - cogs_v - comm if r.cost_price is not None else None
            margin_pct = (margin / rev * 100) if (margin is not None and rev) else None
            top_products.append(TopProduct(
                product_id=str(r.pid),
                name=r.name,
                offer_id=r.offer_id,
                image_url=image_map.get(r.pid),
                revenue=round(rev, 2),
                orders=int(r.orders or 0),
                units=int(r.units or 0),
                margin=round(margin, 2) if margin is not None else None,
                margin_pct=round(margin_pct, 1) if margin_pct is not None else None,
            ))

    # ===== Clusters =====
    clusters: list[ClusterSegment] = []
    if accs:
        cluster_rows = (await db.execute(
            select(
                func.coalesce(Order.cluster_from, "(не определён)").label("cluster"),
                func.coalesce(func.sum(Order.total_amount), 0).label("revenue"),
                func.count(Order.id).label("orders"),
            )
            .where(
                Order.ozon_account_id.in_(accs),
                Order.order_created_at >= dt_from,
                Order.order_created_at < dt_to,
                Order.status == "delivered",
            )
            .group_by("cluster")
            .order_by(desc("revenue"))
            .limit(20)
        )).all()
        total_cluster_rev = sum(float(r.revenue or 0) for r in cluster_rows) or 1
        for r in cluster_rows:
            rev = float(r.revenue or 0)
            clusters.append(ClusterSegment(
                cluster=str(r.cluster),
                revenue=round(rev, 2),
                orders=int(r.orders or 0),
                pct=round(rev / total_cluster_rev * 100, 1),
            ))

    # ===== Missing costs =====
    from app.models.cost import CostConfidence, ProductCostHistory
    latest_subq = (
        select(
            ProductCostHistory.product_id,
            func.max(ProductCostHistory.effective_from).label("latest"),
        )
        .group_by(ProductCostHistory.product_id)
        .subquery()
    )
    missing_n = 0
    if accs:
        missing_n = int((await db.execute(
            select(func.count(Product.id))
            .select_from(Product)
            .outerjoin(latest_subq, latest_subq.c.product_id == Product.id)
            .outerjoin(
                ProductCostHistory,
                (ProductCostHistory.product_id == Product.id)
                & (ProductCostHistory.effective_from == latest_subq.c.latest),
            )
            .where(
                Product.ozon_account_id.in_(accs),
                Product.deleted_at.is_(None),
                (Product.cost_price.is_(None))
                | (ProductCostHistory.confidence == CostConfidence.MISSING.value),
            )
        )).scalar() or 0)

    return DashboardV2Response(
        period_from=date_from.isoformat(),
        period_to=date_to.isoformat(),
        granularity=granularity,
        compare=compare,
        has_missing_costs=missing_n > 0,
        missing_costs_count=missing_n,
        kpi=KPIBlock(
            ordered_revenue=round(k["ordered_revenue"], 2),
            ordered_count=k["ordered_count"],
            ordered_change_pct=_pct(k["ordered_revenue"], p_ordered) if cmp else None,
            revenue=round(revenue, 2),
            revenue_change_pct=_pct(revenue, p_rev) if cmp else None,
            delivered_count=k["delivered_count"],
            in_transit_revenue=round(k["in_transit_revenue"], 2),
            cancelled_revenue=round(k["cancelled_revenue"], 2),
            cancelled_count=k["cancelled_count"],
            gross_profit=round(gross_profit, 2),
            gross_profit_change_pct=_pct(gross_profit, p_gross) if cmp else None,
            orders_count=orders,
            orders_change_pct=_pct(orders, p_ord) if cmp else None,
            aov=round(aov, 2),
            aov_change_pct=_pct(aov, p_aov) if cmp else None,
            ozon_expenses=round(ozon_exp, 2),
            expense_share_pct=round(expense_share, 1) if expense_share else None,
            sparkline=sparkline[-30:],
        ),
        series=series,
        expense_breakdown=expense_breakdown,
        top_products=top_products,
        clusters=clusters,
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
