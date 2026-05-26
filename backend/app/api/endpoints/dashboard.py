"""
Dashboard endpoints — главные метрики продаж.

Сейчас базовая версия:
- KPI за период (выручка, прибыль, заказы, маржа)
- График продаж по дням
- Топ товаров
- По магазинам отдельно или все вместе
"""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Order, OzonAccount, Product, User

router = APIRouter()


# === Pydantic схемы ===

class KPIResponse(BaseModel):
    """KPI плитки для главной."""
    revenue: float
    revenue_change_pct: float | None
    orders_count: int
    orders_change_pct: float | None
    avg_order_value: float
    aov_change_pct: float | None


class DailySalesPoint(BaseModel):
    """Точка на графике продаж."""
    date: str
    revenue: float
    orders: int


class TopProduct(BaseModel):
    """Топ товар."""
    product_id: str
    name: str
    revenue: float
    orders: int


class DashboardResponse(BaseModel):
    """Полный ответ dashboard."""
    period_from: str
    period_to: str
    kpi: KPIResponse
    daily_sales: list[DailySalesPoint]
    top_products: list[TopProduct]


# === Endpoints ===

@router.get("/", response_model=DashboardResponse)
async def get_dashboard(
    days: int = Query(30, ge=1, le=365),
    ozon_account_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """
    Главный Dashboard с KPI за период.

    Параметры:
    - days: за сколько дней показывать (по умолчанию 30)
    - ozon_account_id: фильтр по магазину (если null — все 4 магазина)
    """
    now = datetime.now(UTC)
    period_to = now
    period_from = now - timedelta(days=days)
    previous_from = period_from - timedelta(days=days)

    # === Основной запрос (текущий период) ===
    base_query = (
        select(
            func.coalesce(func.sum(Order.total_amount), 0).label("revenue"),
            func.count(Order.id).label("orders_count"),
        )
        .join(OzonAccount, Order.ozon_account_id == OzonAccount.id)
        .where(
            OzonAccount.company_id == current_user.company_id,
            Order.order_created_at >= period_from,
            Order.order_created_at < period_to,
            Order.status.notin_(["cancelled", "not_accepted"]),
        )
    )

    if ozon_account_id:
        base_query = base_query.where(Order.ozon_account_id == ozon_account_id)

    result = await db.execute(base_query)
    row = result.one()
    revenue = float(row.revenue or 0)
    orders_count = int(row.orders_count or 0)
    aov = revenue / orders_count if orders_count > 0 else 0

    # === Предыдущий период (для сравнения) ===
    prev_query = (
        select(
            func.coalesce(func.sum(Order.total_amount), 0).label("revenue"),
            func.count(Order.id).label("orders_count"),
        )
        .join(OzonAccount, Order.ozon_account_id == OzonAccount.id)
        .where(
            OzonAccount.company_id == current_user.company_id,
            Order.order_created_at >= previous_from,
            Order.order_created_at < period_from,
            Order.status.notin_(["cancelled", "not_accepted"]),
        )
    )
    if ozon_account_id:
        prev_query = prev_query.where(Order.ozon_account_id == ozon_account_id)

    prev_result = await db.execute(prev_query)
    prev_row = prev_result.one()
    prev_revenue = float(prev_row.revenue or 0)
    prev_orders = int(prev_row.orders_count or 0)
    prev_aov = prev_revenue / prev_orders if prev_orders > 0 else 0

    def pct_change(current: float, previous: float) -> float | None:
        if previous == 0:
            return None
        return round((current - previous) / previous * 100, 1)

    # === График по дням ===
    daily_query = (
        select(
            func.date_trunc("day", Order.order_created_at).label("day"),
            func.coalesce(func.sum(Order.total_amount), 0).label("revenue"),
            func.count(Order.id).label("orders"),
        )
        .join(OzonAccount, Order.ozon_account_id == OzonAccount.id)
        .where(
            OzonAccount.company_id == current_user.company_id,
            Order.order_created_at >= period_from,
            Order.order_created_at < period_to,
            Order.status.notin_(["cancelled", "not_accepted"]),
        )
        .group_by("day")
        .order_by("day")
    )
    if ozon_account_id:
        daily_query = daily_query.where(Order.ozon_account_id == ozon_account_id)

    daily_result = await db.execute(daily_query)
    daily_sales = [
        DailySalesPoint(
            date=r.day.strftime("%Y-%m-%d") if r.day else "",
            revenue=float(r.revenue or 0),
            orders=int(r.orders or 0),
        )
        for r in daily_result.all()
    ]

    # === Топ товаров ===
    # TODO: добавить когда будут OrderItem с привязкой к Product
    top_products: list[TopProduct] = []

    return DashboardResponse(
        period_from=period_from.isoformat(),
        period_to=period_to.isoformat(),
        kpi=KPIResponse(
            revenue=revenue,
            revenue_change_pct=pct_change(revenue, prev_revenue),
            orders_count=orders_count,
            orders_change_pct=pct_change(orders_count, prev_orders),
            avg_order_value=round(aov, 2),
            aov_change_pct=pct_change(aov, prev_aov),
        ),
        daily_sales=daily_sales,
        top_products=top_products,
    )
