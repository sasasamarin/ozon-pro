"""
Единый источник «выручки» для всех endpoints.

В коде раньше 4 разных источника (см. AUDIT.md A2):
- Order.total_amount        — buyer-side (что заказали)
- OrderItem.total_price     — то же по items
- AnalyticsDaily.revenue    — buyer-side из аналитики Ozon
- Transaction.accruals_for_sale — seller-side (что Ozon начислил)

Каждое endpoint выбирало свой → юзер видел разные числа в dashboard/funnel/orders/p&l.

Этот helper даёт три явных понятия с source-флагом:

  seller_revenue_for(period, accs) → float
    Что Ozon реально начислил продавцу (Transaction.accruals_for_sale
    WHERE op_type=OperationAgentDeliveredToCustomer).
    Включает Баллы за скидки + Программы партнёров. ИСТИНА для P&L.
    Контур: 'operational'.

  buyer_revenue_for(period, accs) → float
    Что покупатель РЕАЛЬНО заплатил (после СПП). Берём из
    customer_price_monthly_estimate × qty за месяц + actual customer_price
    для свежих 90 дней. Маркетинговый слой.
    Контур: оценка (estimated за старые периоды).

  ordered_value_for(period, accs) → float
    Сумма заказов по цене продавца (Order.total_amount). Не доставлено
    ≠ продано. Это «Заказано в кабинете Ozon». Для воронки и dashboard.

Использование:
    sr = await seller_revenue_for(db, accs, dt_from, dt_to)
    br = await buyer_revenue_for(db, accs, dt_from, dt_to)
    print(f"Заказано: {ov:,.0f} | Продавцу начислено: {sr:,.0f} | Покупатель заплатил: {br:,.0f}")
"""
from __future__ import annotations

import uuid
from datetime import datetime
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class RevenueResult:
    value: float
    source: Literal["api", "db_aggregate", "estimated"]
    contour: Literal["operational", "official", None] = None
    note: str = ""


async def seller_revenue_for(
    db: AsyncSession, *,
    account_ids: list[uuid.UUID],
    dt_from: datetime, dt_to: datetime,
    product_id: uuid.UUID | None = None,
) -> RevenueResult:
    """
    Seller revenue из Transaction.accruals_for_sale —
    единственный правильный источник для P&L (Принципы Flowoi §2).
    """
    if not account_ids:
        return RevenueResult(0.0, "db_aggregate", "operational", "Нет кабинетов")
    params: dict = {
        "accs": [str(a) for a in account_ids],
        "df": dt_from, "dt": dt_to,
    }
    where = ["t.ozon_account_id = ANY(:accs)",
             "t.operation_date >= :df", "t.operation_date < :dt",
             "t.operation_type = 'OperationAgentDeliveredToCustomer'"]
    if product_id:
        # per-SKU невозможно для transactions (накапливается на posting, не SKU).
        # Если важно — фильтруем по posting_number → orders по этому SKU.
        where.append("""t.posting_number IN (
            SELECT DISTINCT o.posting_number FROM orders o
            JOIN order_items oi ON oi.order_id = o.id
            WHERE oi.product_id = :pid
        )""")
        params["pid"] = str(product_id)

    r = (await db.execute(text(f"""
        SELECT COALESCE(SUM(t.accruals_for_sale), 0)::float AS rev
        FROM transactions t
        WHERE {' AND '.join(where)}
    """), params)).scalar() or 0
    return RevenueResult(
        value=float(r),
        source="db_aggregate",
        contour="operational",
        note="accruals_for_sale = Выручка + Баллы + Программы партнёров. "
             "Контур: оперативный (из транзакций).",
    )


async def buyer_revenue_for(
    db: AsyncSession, *,
    account_ids: list[uuid.UUID],
    dt_from: datetime, dt_to: datetime,
) -> RevenueResult:
    """
    Buyer revenue = Σ customer_price × qty.

    Для свежих заказов customer_price берётся из order_items
    (заполнен sync'ом enrich_customer_price через /v2/posting/fbo/get).
    Для старых месяцев — оценка из customer_price_monthly_estimate.

    Это маркетинговый слой ('сколько покупатель заплатил после СПП').
    НЕ путать с seller_revenue.
    """
    if not account_ids:
        return RevenueResult(0.0, "estimated", None, "Нет кабинетов")
    params: dict = {
        "accs": [str(a) for a in account_ids],
        "df": dt_from, "dt": dt_to,
    }
    r = (await db.execute(text("""
        SELECT
          COALESCE(SUM(oi.customer_price * oi.quantity) FILTER (WHERE oi.customer_price IS NOT NULL), 0)::float AS exact,
          COUNT(*) FILTER (WHERE oi.customer_price IS NULL) AS missing_items
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        WHERE o.ozon_account_id = ANY(:accs)
          AND o.order_created_at >= :df AND o.order_created_at < :dt
          AND o.status = 'delivered'
    """), params)).first()

    exact = float(r.exact or 0)
    missing = int(r.missing_items or 0)
    return RevenueResult(
        value=exact,
        source="api" if missing == 0 else "estimated",
        contour=None,
        note=(
            "customer_price из order_items (точно из /v2/posting/fbo/get)."
            + (f" Пропущено {missing} items без customer_price." if missing else "")
        ),
    )


async def ordered_value_for(
    db: AsyncSession, *,
    account_ids: list[uuid.UUID],
    dt_from: datetime, dt_to: datetime,
    product_id: uuid.UUID | None = None,
    status_filter: Literal["all", "delivered", "in_transit"] = "all",
) -> RevenueResult:
    """
    Сумма заказов по цене продавца — то что «Заказано» в кабинете Ozon.

    Не равно seller_revenue (Ozon начисляет ПОСЛЕ доставки и с Баллами).
    Не равно buyer_revenue (покупатель платит со СПП).

    Для dashboard «Заказано на сумму», воронка «Заказы ₽».
    """
    if not account_ids:
        return RevenueResult(0.0, "db_aggregate", None, "Нет кабинетов")
    params: dict = {
        "accs": [str(a) for a in account_ids],
        "df": dt_from, "dt": dt_to,
    }
    where = [
        "o.ozon_account_id = ANY(:accs)",
        "o.order_created_at >= :df",
        "o.order_created_at < :dt",
    ]
    if status_filter == "delivered":
        where.append("o.status = 'delivered'")
    elif status_filter == "in_transit":
        where.append("o.status IN ('delivering','awaiting_packaging','awaiting_deliver')")
    if product_id:
        where.append("oi.product_id = :pid")
        params["pid"] = str(product_id)

    r = (await db.execute(text(f"""
        SELECT COALESCE(SUM(oi.price * oi.quantity), 0)::float AS rev
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        WHERE {' AND '.join(where)}
    """), params)).scalar() or 0
    return RevenueResult(
        value=float(r),
        source="db_aggregate",
        contour=None,
        note=(
            f"OrderItem.price (seller_price) × qty по статусу '{status_filter}'. "
            "НЕ seller_revenue (нет Баллов/Партнёров)."
        ),
    )
