"""
Dashboard endpoints — главные метрики.

Считаем за период:
- KPI: выручка, расходы Ozon, валовая прибыль (с учётом cost_price), заказы, AOV
- Декомпозиция расходов из transactions.services[] (разнесённых полей)
- Топ-5 товаров по выручке
- Daily-series для графика (revenue / expenses / profit по дням)

ВАЖНО про себестоимость:
- products.cost_price хранит latest manual entry (заполняется через
  product_cost_history). 100₽ confidence='missing' = заглушка → UI должен
  показать <CostWarningBanner /> и плашку «прибыль приблизительная».
- has_missing_costs / missing_costs_count в ответе.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.deps_cabinets import get_accessible_cabinet_ids
from app.db.session import get_db
from app.models import Order, OrderItem, OzonAccount, Product, Transaction, User
from app.models.cost import CostConfidence, ProductCostHistory

router = APIRouter()


# === Pydantic schemas ===

class KPIResponse(BaseModel):
    revenue: float
    revenue_change_pct: float | None
    ozon_expenses: float
    ozon_expenses_pct_of_revenue: float | None
    gross_profit: float
    gross_profit_change_pct: float | None
    orders_count: int
    orders_change_pct: float | None
    avg_order_value: float


class ExpenseRow(BaseModel):
    category: str
    amount: float
    pct_of_expenses: float


class DailyPoint(BaseModel):
    date: str
    revenue: float
    expenses: float
    profit: float


class TopProduct(BaseModel):
    product_id: str
    name: str
    offer_id: str
    revenue: float
    units: int
    share_pct: float


class DashboardResponse(BaseModel):
    period_from: str
    period_to: str
    cabinet_ids: list[str]

    has_missing_costs: bool
    missing_costs_count: int

    kpi: KPIResponse
    expense_breakdown: list[ExpenseRow]
    daily_series: list[DailyPoint]
    top_products: list[TopProduct]


# === Helpers ===

# Транзакционные «корзины» с человеческими ярлыками.
_EXPENSE_BUCKETS = [
    ("Комиссия Ozon", "sale_commission"),
    ("Логистика к клиенту", "delivery_to_customer"),
    ("Возвратная логистика", "return_logistics"),
    ("Last mile", "last_mile"),
    ("Хранение", "storage"),
    ("Размещение", "placement"),
    ("Эквайринг", "acquiring"),
    ("Реклама", "advertising"),
    ("Утилизация", "utilization"),
    ("Штрафы", "fine"),
]


async def _account_ids(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    cabinet_ids: list[uuid.UUID] | None,
    accessible: list[uuid.UUID] | None = None,
) -> list[uuid.UUID]:
    q = select(OzonAccount.id).where(
        OzonAccount.company_id == company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if cabinet_ids:
        q = q.where(OzonAccount.id.in_(cabinet_ids))
    if accessible is not None:
        q = q.where(OzonAccount.id.in_(accessible))
    return [r[0] for r in (await db.execute(q)).all()]


async def _revenue_and_orders(
    db: AsyncSession,
    *,
    account_ids: list[uuid.UUID],
    period_from: datetime,
    period_to: datetime,
) -> tuple[float, int]:
    if not account_ids:
        return 0.0, 0
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(Order.total_amount), 0).label("revenue"),
                func.count(Order.id).label("orders"),
            ).where(
                Order.ozon_account_id.in_(account_ids),
                Order.order_created_at >= period_from,
                Order.order_created_at < period_to,
                Order.status == "delivered",
            )
        )
    ).one()
    return float(row.revenue or 0), int(row.orders or 0)


async def _ozon_expenses_breakdown(
    db: AsyncSession,
    *,
    account_ids: list[uuid.UUID],
    period_from: datetime,
    period_to: datetime,
) -> dict[str, float]:
    """SUM каждой корзины из transactions за период.

    Ozon в `services[]` хранит отрицательные суммы, мы при синке разносим
    в правильные поля как ОТРИЦАТЕЛЬНЫЕ значения. Берём ABS для отображения.
    sale_commission тоже отрицательная.
    """
    if not account_ids:
        return {label: 0.0 for label, _ in _EXPENSE_BUCKETS}
    cols = [
        func.coalesce(func.sum(func.abs(getattr(Transaction, field))), 0).label(field)
        for _, field in _EXPENSE_BUCKETS
    ]
    row = (
        await db.execute(
            select(*cols).where(
                Transaction.ozon_account_id.in_(account_ids),
                Transaction.time >= period_from,
                Transaction.time < period_to,
            )
        )
    ).one()
    return {
        label: float(getattr(row, field) or 0)
        for label, field in _EXPENSE_BUCKETS
    }


async def _cogs_for_period(
    db: AsyncSession,
    *,
    account_ids: list[uuid.UUID],
    period_from: datetime,
    period_to: datetime,
) -> float:
    """COGS = SUM(quantity × current cost_price) для delivered заказов за период.

    Использует products.cost_price (denormalized). Когда юзер заполнит точную
    себестоимость через форму — это поле обновится → пересчёт автоматический.
    """
    if not account_ids:
        return 0.0
    row = await db.execute(
        select(
            func.coalesce(
                func.sum(OrderItem.quantity * func.coalesce(Product.cost_price, 0)), 0
            )
        )
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            Order.ozon_account_id.in_(account_ids),
            Order.order_created_at >= period_from,
            Order.order_created_at < period_to,
            Order.status == "delivered",
        )
    )
    return float(row.scalar() or 0)


async def _daily_series(
    db: AsyncSession,
    *,
    account_ids: list[uuid.UUID],
    period_from: datetime,
    period_to: datetime,
) -> list[DailyPoint]:
    """Daily revenue + expenses + profit (учитывая cost_price)."""
    if not account_ids:
        return []

    # Revenue по дням
    rev_rows = (
        await db.execute(
            select(
                func.date_trunc("day", Order.order_created_at).label("d"),
                func.coalesce(func.sum(Order.total_amount), 0).label("revenue"),
            )
            .where(
                Order.ozon_account_id.in_(account_ids),
                Order.order_created_at >= period_from,
                Order.order_created_at < period_to,
                Order.status == "delivered",
            )
            .group_by("d")
            .order_by("d")
        )
    ).all()
    revenue_by_day = {r.d.date().isoformat(): float(r.revenue or 0) for r in rev_rows}

    # COGS по дням
    cogs_rows = (
        await db.execute(
            select(
                func.date_trunc("day", Order.order_created_at).label("d"),
                func.coalesce(
                    func.sum(OrderItem.quantity * func.coalesce(Product.cost_price, 0)), 0
                ).label("cogs"),
            )
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id)
            .where(
                Order.ozon_account_id.in_(account_ids),
                Order.order_created_at >= period_from,
                Order.order_created_at < period_to,
                Order.status == "delivered",
            )
            .group_by("d")
            .order_by("d")
        )
    ).all()
    cogs_by_day = {r.d.date().isoformat(): float(r.cogs or 0) for r in cogs_rows}

    # Расходы Ozon по дням (sum всех корзин)
    expense_cols_sum = sum(
        [func.coalesce(func.abs(getattr(Transaction, field)), 0) for _, field in _EXPENSE_BUCKETS],
        start=func.coalesce(func.abs(Transaction.sale_commission), 0) * 0,  # zero init
    )
    exp_rows = (
        await db.execute(
            select(
                func.date_trunc("day", Transaction.time).label("d"),
                func.coalesce(func.sum(expense_cols_sum), 0).label("expenses"),
            )
            .where(
                Transaction.ozon_account_id.in_(account_ids),
                Transaction.time >= period_from,
                Transaction.time < period_to,
            )
            .group_by("d")
            .order_by("d")
        )
    ).all()
    expenses_by_day = {r.d.date().isoformat(): float(r.expenses or 0) for r in exp_rows}

    # Объединяем — берём все даты в окне
    all_dates = set(revenue_by_day) | set(expenses_by_day) | set(cogs_by_day)
    points: list[DailyPoint] = []
    for d in sorted(all_dates):
        rev = revenue_by_day.get(d, 0.0)
        exp = expenses_by_day.get(d, 0.0)
        cogs = cogs_by_day.get(d, 0.0)
        points.append(
            DailyPoint(
                date=d,
                revenue=round(rev, 2),
                expenses=round(exp + cogs, 2),
                profit=round(rev - exp - cogs, 2),
            )
        )
    return points


async def _top_products(
    db: AsyncSession,
    *,
    account_ids: list[uuid.UUID],
    period_from: datetime,
    period_to: datetime,
    total_revenue: float,
    limit: int = 5,
) -> list[TopProduct]:
    if not account_ids:
        return []
    rows = (
        await db.execute(
            select(
                Product.id.label("pid"),
                Product.name.label("name"),
                Product.offer_id.label("offer_id"),
                func.coalesce(func.sum(OrderItem.total_price), 0).label("revenue"),
                func.coalesce(func.sum(OrderItem.quantity), 0).label("units"),
            )
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id)
            .where(
                Order.ozon_account_id.in_(account_ids),
                Order.order_created_at >= period_from,
                Order.order_created_at < period_to,
                Order.status == "delivered",
            )
            .group_by(Product.id, Product.name, Product.offer_id)
            .order_by(func.sum(OrderItem.total_price).desc())
            .limit(limit)
        )
    ).all()
    return [
        TopProduct(
            product_id=str(r.pid),
            name=r.name,
            offer_id=r.offer_id,
            revenue=round(float(r.revenue or 0), 2),
            units=int(r.units or 0),
            share_pct=round((float(r.revenue or 0) / total_revenue * 100) if total_revenue > 0 else 0, 1),
        )
        for r in rows
    ]


async def _missing_costs_count(
    db: AsyncSession, *, account_ids: list[uuid.UUID]
) -> tuple[bool, int]:
    """Сколько активных товаров имеют либо NULL cost_price, либо последнюю
    запись в product_cost_history с confidence='missing'.
    """
    if not account_ids:
        return False, 0
    # Latest cost entry per product
    latest_subq = (
        select(
            ProductCostHistory.product_id,
            func.max(ProductCostHistory.effective_from).label("latest"),
        )
        .group_by(ProductCostHistory.product_id)
        .subquery()
    )
    row = (
        await db.execute(
            select(func.count(Product.id))
            .select_from(Product)
            .outerjoin(latest_subq, latest_subq.c.product_id == Product.id)
            .outerjoin(
                ProductCostHistory,
                (ProductCostHistory.product_id == Product.id)
                & (ProductCostHistory.effective_from == latest_subq.c.latest),
            )
            .where(
                Product.ozon_account_id.in_(account_ids),
                Product.deleted_at.is_(None),
                (Product.cost_price.is_(None))
                | (ProductCostHistory.confidence == CostConfidence.MISSING.value),
            )
        )
    ).scalar() or 0
    count = int(row)
    return count > 0, count


# === Endpoints ===

def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


@router.get("/", response_model=DashboardResponse)
async def get_dashboard(
    days: int = Query(30, ge=1, le=365),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """Главная сводка: выручка/расходы/прибыль за период по multi-select кабинетам."""
    now = datetime.now(UTC)
    period_to = now
    period_from = now - timedelta(days=days)
    prev_from = period_from - timedelta(days=days)

    accessible = await get_accessible_cabinet_ids(db, current_user)
    accounts = await _account_ids(
        db,
        company_id=current_user.company_id,
        cabinet_ids=cabinet_ids,
        accessible=accessible,
    )

    revenue, orders_count = await _revenue_and_orders(
        db, account_ids=accounts, period_from=period_from, period_to=period_to
    )
    prev_revenue, prev_orders = await _revenue_and_orders(
        db, account_ids=accounts, period_from=prev_from, period_to=period_from
    )

    expense_dict = await _ozon_expenses_breakdown(
        db, account_ids=accounts, period_from=period_from, period_to=period_to
    )
    prev_expense_dict = await _ozon_expenses_breakdown(
        db, account_ids=accounts, period_from=prev_from, period_to=period_from
    )

    ozon_expenses_total = sum(expense_dict.values())
    prev_expenses_total = sum(prev_expense_dict.values())

    cogs = await _cogs_for_period(
        db, account_ids=accounts, period_from=period_from, period_to=period_to
    )
    prev_cogs = await _cogs_for_period(
        db, account_ids=accounts, period_from=prev_from, period_to=period_from
    )

    gross_profit = revenue - cogs - ozon_expenses_total
    prev_gross_profit = prev_revenue - prev_cogs - prev_expenses_total

    aov = revenue / orders_count if orders_count > 0 else 0

    # Breakdown — сортируем по убыванию суммы, отбрасываем нулевые
    breakdown = []
    for label, amount in sorted(expense_dict.items(), key=lambda kv: kv[1], reverse=True):
        if amount > 0:
            breakdown.append(
                ExpenseRow(
                    category=label,
                    amount=round(amount, 2),
                    pct_of_expenses=round(
                        (amount / ozon_expenses_total * 100) if ozon_expenses_total > 0 else 0, 1
                    ),
                )
            )

    daily = await _daily_series(
        db, account_ids=accounts, period_from=period_from, period_to=period_to
    )
    top = await _top_products(
        db, account_ids=accounts, period_from=period_from, period_to=period_to,
        total_revenue=revenue,
    )
    has_missing, missing_count = await _missing_costs_count(db, account_ids=accounts)

    return DashboardResponse(
        period_from=period_from.date().isoformat(),
        period_to=period_to.date().isoformat(),
        cabinet_ids=[str(x) for x in (cabinet_ids or accounts)],
        has_missing_costs=has_missing,
        missing_costs_count=missing_count,
        kpi=KPIResponse(
            revenue=round(revenue, 2),
            revenue_change_pct=_pct_change(revenue, prev_revenue),
            ozon_expenses=round(ozon_expenses_total, 2),
            ozon_expenses_pct_of_revenue=round(
                (ozon_expenses_total / revenue * 100) if revenue > 0 else 0, 1
            ),
            gross_profit=round(gross_profit, 2),
            gross_profit_change_pct=_pct_change(gross_profit, prev_gross_profit),
            orders_count=orders_count,
            orders_change_pct=_pct_change(orders_count, prev_orders),
            avg_order_value=round(aov, 2),
        ),
        expense_breakdown=breakdown,
        daily_series=daily,
        top_products=top,
    )
