"""
P&L декомпозиция за период.

Шаги (сверху вниз):
  Выручка
  − Себестоимость (units_delivered × cost_price)
  = Валовая прибыль
  − Комиссия Ozon (sale_commission)
  − Логистика к клиенту (delivery_to_customer)
  − Возвратная логистика (return_logistics)
  − Last mile
  − Хранение (storage)
  − Размещение (placement)
  − Эквайринг (acquiring)
  − Реклама (advertising)
  − Утилизация (utilization)
  = Маржинальная прибыль

GET /api/v1/finance/pnl?days=30&cabinet_ids=...&compare=true
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Company, Order, OrderItem, OzonAccount, Product, Transaction, User
from app.models.cost import CostConfidence, ProductCostHistory
from app.models.loan import LoanPayment
from app.models.marketplace import Return
from app.services.tax import calc_tax

router = APIRouter()
UTC = timezone.utc


class PnLRow(BaseModel):
    label: str
    amount: float
    pct_of_revenue: float | None
    is_subtotal: bool = False
    is_negative: bool = False  # для UI расхода
    # для drill-down: фильтр-параметр на /finance/transactions (опционально)
    transactions_filter: dict | None = None


class PnLResponse(BaseModel):
    period_from: str
    period_to: str
    has_missing_costs: bool
    missing_costs_count: int

    # Две модели выручки (принцип «2 модели финансов»):
    # - seller_revenue: что Ozon реально НАЧИСЛИЛ продавцу
    #   (accruals_for_sale из транзакций). Главная цифра — от неё маржа и налог.
    # - buyer_revenue: что заплатил покупатель (Order.total_amount, после СПП).
    #   Справочно, для понимания «скидки за счёт Ozon».
    # Разница = «Баллы за скидки» + «Программы партнёров» (Ozon доплачивает за СПП).
    seller_revenue: float
    buyer_revenue: float
    revenue: float                # = seller_revenue (legacy alias для frontend)
    returned_revenue: float       # сумма возвратов по return_date в периоде
    effective_revenue: float      # seller_revenue − returned_revenue (база для расчётов и налога)
    cogs: float
    gross_profit: float           # effective_revenue − cogs
    total_ozon_expenses: float
    marginal_profit: float

    # === Налог + чистая прибыль ===
    tax_regime: str
    tax_regime_label: str
    tax_rate_pct: float
    tax_amount: float
    vat_amount: float
    net_profit: float            # marginal_profit − tax − vat
    net_margin_pct: float | None

    rows: list[PnLRow]

    # сравнение с прошлым
    prev_revenue: float | None = None
    prev_marginal_profit: float | None = None
    prev_net_profit: float | None = None


_EXPENSE_BUCKETS = [
    ("Комиссия Ozon",          "sale_commission",       "abs"),
    ("Логистика к клиенту",    "delivery_to_customer",  "pos"),
    ("Возвратная логистика",   "return_logistics",      "pos"),
    ("Last mile",              "last_mile",             "pos"),
    ("Хранение",               "storage",               "pos"),
    ("Размещение",             "placement",             "pos"),
    ("Эквайринг",              "acquiring",             "pos"),
    ("Реклама",                "advertising",           "pos"),
    ("Утилизация",             "utilization",           "pos"),
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


async def _buyer_revenue_for_window(
    db: AsyncSession, *, accs: list[uuid.UUID], dt_from: datetime, dt_to: datetime
) -> float:
    """Что заплатил покупатель (Order.total_amount). Справочно."""
    if not accs:
        return 0.0
    row = await db.execute(
        select(func.coalesce(func.sum(Order.total_amount), 0))
        .where(
            Order.ozon_account_id.in_(accs),
            Order.order_created_at >= dt_from,
            Order.order_created_at < dt_to,
            Order.status == "delivered",
        )
    )
    return float(row.scalar() or 0)


async def _seller_revenue_for_window(
    db: AsyncSession, *, accs: list[uuid.UUID], dt_from: datetime, dt_to: datetime
) -> float:
    """
    Главная выручка — accruals_for_sale из transactions, по operation_date.

    Включает компенсацию «Баллов за скидки» и «Программы партнёров» —
    это деньги, которые Ozon ДОПЛАЧИВАЕТ продавцу за участие в скидках.
    На эту цифру Ozon начисляет комиссию, от неё считается маржа продавца.

    Источник истины — Ozon /v3/finance/transaction/list, operation_type
    OperationAgentDeliveredToCustomer.
    """
    if not accs:
        return 0.0
    row = await db.execute(
        select(func.coalesce(func.sum(Transaction.accruals_for_sale), 0))
        .where(
            Transaction.ozon_account_id.in_(accs),
            Transaction.operation_date >= dt_from,
            Transaction.operation_date < dt_to,
            Transaction.operation_type == "OperationAgentDeliveredToCustomer",
        )
    )
    return float(row.scalar() or 0)


async def _cogs_for_window(
    db: AsyncSession, *, accs: list[uuid.UUID], dt_from: datetime, dt_to: datetime
) -> float:
    if not accs:
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
            Order.ozon_account_id.in_(accs),
            Order.order_created_at >= dt_from,
            Order.order_created_at < dt_to,
            Order.status == "delivered",
        )
    )
    return float(row.scalar() or 0)


async def _expenses_for_window(
    db: AsyncSession, *, accs: list[uuid.UUID], dt_from: datetime, dt_to: datetime
) -> dict[str, float]:
    if not accs:
        return {label: 0.0 for label, _, _ in _EXPENSE_BUCKETS}
    cols = []
    for label, field, mode in _EXPENSE_BUCKETS:
        expr = func.coalesce(func.sum(func.abs(getattr(Transaction, field))), 0)
        cols.append(expr.label(field))
    row = (await db.execute(
        select(*cols).where(
            Transaction.ozon_account_id.in_(accs),
            Transaction.time >= dt_from,
            Transaction.time < dt_to,
        )
    )).one()
    return {label: float(getattr(row, field) or 0) for label, field, _ in _EXPENSE_BUCKETS}


async def _returned_revenue(
    db: AsyncSession, *, accs: list[uuid.UUID],
    dt_from: datetime, dt_to: datetime,
) -> float:
    """Сумма возвратов покупателям по return_date в периоде.

    Принцип «зеркало Ozon»: revenue — это brut (то что показано в кабинете
    как продано), а возвраты — отдельная строка ниже. Налоговая база =
    revenue − returned_revenue (УСН Доходы пускает возвраты в уменьшение).
    """
    if not accs:
        return 0.0
    res = await db.execute(
        select(func.coalesce(func.sum(Return.return_amount), 0))
        .where(
            Return.ozon_account_id.in_(accs),
            Return.return_date >= dt_from,
            Return.return_date < dt_to,
        )
    )
    return float(res.scalar() or 0)


async def _loan_interest_for_window(
    db: AsyncSession, *, company_id: uuid.UUID, dt_from: datetime, dt_to: datetime,
) -> tuple[float, float]:
    """
    Возвращает (interest_part, fee_part) по плановой дате pay_date в окне.

    Тело займа (principal_part) НИКОГДА не учитывается в P&L — оно только
    в ДДС. Это базовое правило ТЗ flowoi_tz_loans.md.

    Метод начисления (pay_date), а не кассовый (paid_at) — стандарт для P&L.
    """
    row = (await db.execute(
        select(
            func.coalesce(func.sum(LoanPayment.interest_part), 0),
            func.coalesce(func.sum(LoanPayment.fee_part), 0),
        ).where(
            LoanPayment.company_id == company_id,
            LoanPayment.pay_date >= dt_from.date(),
            LoanPayment.pay_date <= dt_to.date(),
        )
    )).one()
    return float(row[0] or 0), float(row[1] or 0)


async def _missing_costs(db: AsyncSession, *, accs: list[uuid.UUID]) -> tuple[bool, int]:
    if not accs:
        return False, 0
    latest_subq = (
        select(
            ProductCostHistory.product_id,
            func.max(ProductCostHistory.effective_from).label("latest"),
        )
        .group_by(ProductCostHistory.product_id)
        .subquery()
    )
    cnt = (await db.execute(
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
    )).scalar() or 0
    return int(cnt) > 0, int(cnt)


@router.get("/", response_model=PnLResponse)
async def get_pnl(
    days: int = Query(30, ge=1, le=365),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    compare: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PnLResponse:
    now = datetime.now(UTC)
    period_to = now
    period_from = now - timedelta(days=days)

    accs = await _account_ids(db, company_id=current_user.company_id, cabinet_ids=cabinet_ids)

    seller_revenue = await _seller_revenue_for_window(db, accs=accs, dt_from=period_from, dt_to=period_to)
    buyer_revenue = await _buyer_revenue_for_window(db, accs=accs, dt_from=period_from, dt_to=period_to)
    # Top-line = seller_revenue. Это что Ozon начислил продавцу (incl. компенсации СПП).
    revenue = seller_revenue
    returned_revenue = await _returned_revenue(db, accs=accs, dt_from=period_from, dt_to=period_to)
    effective_revenue = revenue - returned_revenue
    cogs = await _cogs_for_window(db, accs=accs, dt_from=period_from, dt_to=period_to)
    expenses = await _expenses_for_window(db, accs=accs, dt_from=period_from, dt_to=period_to)

    gross_profit = effective_revenue - cogs
    total_expenses = sum(expenses.values())
    marginal_profit = gross_profit - total_expenses

    # Проценты по кредитам (Ветка 1 ТЗ flowoi_tz_loans.md) — финансовый расход.
    # Тело займа в P&L НЕ попадает.
    loan_interest, loan_fee = await _loan_interest_for_window(
        db, company_id=current_user.company_id,
        dt_from=period_from, dt_to=period_to,
    )
    loan_finance_cost = loan_interest + loan_fee
    profit_before_tax = marginal_profit - loan_finance_cost

    has_missing, missing_n = await _missing_costs(db, accs=accs)

    # % считаем от brut-выручки (= что в кабинете Ozon), чтобы юзер видел
    # «возвраты съели X% от продаж» сразу.
    def pct(v: float) -> float | None:
        if revenue == 0:
            return None
        return round(v / revenue * 100, 2)

    rows: list[PnLRow] = [
        PnLRow(label="Выручка продавца (Ozon начислил)", amount=round(seller_revenue, 2),
               pct_of_revenue=100.0 if seller_revenue else None),
    ]
    # Доплата Ozon за СПП = seller_revenue − buyer_revenue. Положительная разница =
    # часть выручки, которую Ozon доплатил продавцу за скидку покупателю.
    spp_compensation = seller_revenue - buyer_revenue
    if abs(spp_compensation) > 1:
        rows.append(PnLRow(
            label=f"   в т.ч. компенсация СПП от Ozon",
            amount=round(spp_compensation, 2),
            pct_of_revenue=pct(spp_compensation),
        ))
        rows.append(PnLRow(
            label=f"   справочно — заплатил покупатель",
            amount=round(buyer_revenue, 2),
            pct_of_revenue=pct(buyer_revenue),
        ))
    if returned_revenue > 0:
        rows.append(PnLRow(
            label="− Возвраты покупателям",
            amount=round(-returned_revenue, 2),
            pct_of_revenue=pct(-returned_revenue),
            is_negative=True,
        ))
        rows.append(PnLRow(
            label="Эффективная выручка",
            amount=round(effective_revenue, 2),
            pct_of_revenue=pct(effective_revenue),
            is_subtotal=True,
        ))
    rows.append(PnLRow(
        label="− Себестоимость (COGS)", amount=round(-cogs, 2),
        pct_of_revenue=pct(-cogs), is_negative=True,
    ))
    rows.append(PnLRow(
        label="ВАЛОВАЯ ПРИБЫЛЬ", amount=round(gross_profit, 2),
        pct_of_revenue=pct(gross_profit), is_subtotal=True,
    ))
    # Сортируем расходные бакеты по убыванию суммы
    for label, amount in sorted(expenses.items(), key=lambda kv: kv[1], reverse=True):
        # transactions_filter — для drill-down кликом на строку
        rows.append(PnLRow(
            label=f"− {label}",
            amount=round(-amount, 2),
            pct_of_revenue=pct(-amount),
            is_negative=True,
            # фильтр по бакету через operation_type не возможен напрямую (бакет
            # это услуга в services[], не op_type). Пока без drill, юзер
            # понимает порядок: сумма из transactions с этим service-name.
        ))
    rows.append(PnLRow(
        label="МАРЖИНАЛЬНАЯ ПРИБЫЛЬ",
        amount=round(marginal_profit, 2),
        pct_of_revenue=pct(marginal_profit),
        is_subtotal=True,
    ))

    # Проценты по кредитам — финансовый расход (между маржой и налогом).
    # Тело займа в P&L НЕ показывается вообще, оно только в ДДС.
    if loan_finance_cost > 0:
        rows.append(PnLRow(
            label="− Проценты по кредитам",
            amount=round(-loan_finance_cost, 2),
            pct_of_revenue=pct(-loan_finance_cost),
            is_negative=True,
        ))
        rows.append(PnLRow(
            label="ПРИБЫЛЬ ДО НАЛОГА",
            amount=round(profit_before_tax, 2),
            pct_of_revenue=pct(profit_before_tax),
            is_subtotal=True,
        ))

    # === Налог по компании-режиму ===
    company = (await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )).scalar_one()
    tax_regime = company.tax_regime or "usn_income"
    tax_rate = float(company.tax_rate_pct or 6.0)
    vat_rate = float(company.vat_rate_pct) if company.vat_rate_pct else None
    # База налога — effective_revenue (после возвратов).
    # УСН Доходы: возвраты по ФНС уменьшают налоговую базу.
    # УСН Дох-Расх / ОСНО: налог от прибыли, где revenue уже без возвратов.
    # На УСН Дох-Расх и ОСНО проценты по кредитам уменьшают налоговую базу
    # (gross_profit = profit_before_tax). На УСН Доходы base = revenue, проценты
    # на налог не влияют — calc_tax сам это учитывает по tax_regime.
    tax_res = calc_tax(
        revenue=effective_revenue, gross_profit=profit_before_tax,
        tax_regime=tax_regime, tax_rate_pct=tax_rate, vat_rate_pct=vat_rate,
    )
    if tax_res.vat_amount > 0:
        rows.append(PnLRow(
            label=f"− НДС ({vat_rate}%)",
            amount=round(-tax_res.vat_amount, 2),
            pct_of_revenue=pct(-tax_res.vat_amount),
            is_negative=True,
        ))
    rows.append(PnLRow(
        label=f"− Налог {tax_res.regime_label} ({tax_res.rate_pct}% от {tax_res.base_label})",
        amount=round(-tax_res.tax_amount, 2),
        pct_of_revenue=pct(-tax_res.tax_amount),
        is_negative=True,
    ))
    rows.append(PnLRow(
        label="ЧИСТАЯ ПРИБЫЛЬ",
        amount=tax_res.net_profit,
        pct_of_revenue=pct(tax_res.net_profit),
        is_subtotal=True,
    ))

    prev_revenue: float | None = None
    prev_marginal: float | None = None
    prev_net: float | None = None
    if compare:
        prev_from = period_from - timedelta(days=days)
        prev_to = period_from
        pr_rev = await _seller_revenue_for_window(db, accs=accs, dt_from=prev_from, dt_to=prev_to)
        pr_returned = await _returned_revenue(db, accs=accs, dt_from=prev_from, dt_to=prev_to)
        pr_eff = pr_rev - pr_returned
        pr_cogs = await _cogs_for_window(db, accs=accs, dt_from=prev_from, dt_to=prev_to)
        pr_exp = await _expenses_for_window(db, accs=accs, dt_from=prev_from, dt_to=prev_to)
        pr_int, pr_fee = await _loan_interest_for_window(
            db, company_id=current_user.company_id,
            dt_from=prev_from, dt_to=prev_to,
        )
        prev_revenue = pr_rev
        prev_marginal = pr_eff - pr_cogs - sum(pr_exp.values())
        prev_profit_before_tax = prev_marginal - (pr_int + pr_fee)
        prev_tax = calc_tax(
            revenue=pr_eff, gross_profit=prev_profit_before_tax,
            tax_regime=tax_regime, tax_rate_pct=tax_rate, vat_rate_pct=vat_rate,
        )
        prev_net = prev_tax.net_profit

    net_margin = (tax_res.net_profit / revenue * 100) if revenue else None
    return PnLResponse(
        period_from=period_from.date().isoformat(),
        period_to=period_to.date().isoformat(),
        has_missing_costs=has_missing,
        missing_costs_count=missing_n,
        seller_revenue=round(seller_revenue, 2),
        buyer_revenue=round(buyer_revenue, 2),
        revenue=round(revenue, 2),
        returned_revenue=round(returned_revenue, 2),
        effective_revenue=round(effective_revenue, 2),
        cogs=round(cogs, 2),
        gross_profit=round(gross_profit, 2),
        total_ozon_expenses=round(total_expenses, 2),
        marginal_profit=round(marginal_profit, 2),
        tax_regime=tax_regime,
        tax_regime_label=tax_res.regime_label,
        tax_rate_pct=tax_rate,
        tax_amount=tax_res.tax_amount,
        vat_amount=tax_res.vat_amount,
        net_profit=tax_res.net_profit,
        net_margin_pct=round(net_margin, 2) if net_margin is not None else None,
        rows=rows,
        prev_revenue=round(prev_revenue, 2) if prev_revenue is not None else None,
        prev_marginal_profit=round(prev_marginal, 2) if prev_marginal is not None else None,
        prev_net_profit=round(prev_net, 2) if prev_net is not None else None,
    )
