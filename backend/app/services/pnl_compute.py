"""
Чистая (без БД) математика P&L — единый источник формулы прибыли.

Вынесено из endpoints/pnl.py, чтобы:
  1. формула жила в ОДНОМ месте (текущий период и период сравнения больше её
     не дублируют);
  2. её можно было покрыть golden-тестом без БД
     (tests/services/test_pnl_compute.py).

Инварианты (CLAUDE.md «Формула P&L», выверено на Crema Viva, diff=0):
  seller_revenue   = Выручка + Баллы за скидки + Программы партнёров
                     (Баллы за скидки — ПРИТОК, НЕ вычитать!)
  effective_revenue = seller_revenue − возвраты покупателям
  валовая          = effective_revenue − себестоимость
  маржинальная     = валовая − комиссии/услуги Ozon
  до налога        = маржинальная − проценты по кредитам
                     (ТЕЛО займа в P&L НЕ входит — только % и комиссии)
  чистая           = до налога − налог
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.tax import TaxResult, calc_tax


@dataclass
class PnLResult:
    seller_revenue: float
    buyer_revenue: float
    spp_compensation: float        # = seller_revenue − buyer_revenue (доплата Ozon за СПП)
    returned_revenue: float
    effective_revenue: float
    cogs: float
    gross_profit: float
    total_expenses: float
    marginal_profit: float
    loan_finance_cost: float       # проценты + комиссии по займам (НЕ тело долга)
    profit_before_tax: float
    tax: TaxResult


def compute_pnl(
    *,
    seller_revenue: float,
    buyer_revenue: float = 0.0,
    returned_revenue: float = 0.0,
    cogs: float = 0.0,
    expenses: dict[str, float] | None = None,
    loan_interest: float = 0.0,
    loan_fee: float = 0.0,
    tax_regime: str = "usn_income",
    tax_rate_pct: float = 6.0,
    vat_rate_pct: float | None = None,
) -> PnLResult:
    """Собирает P&L из уже посчитанных компонентов. Чистая функция, без I/O.

    expenses — словарь {название_статьи: положительная_сумма_расхода}.
    Все суммы — в рублях (положительные значения расходов/возвратов).
    """
    expenses = expenses or {}
    revenue = seller_revenue
    effective_revenue = revenue - returned_revenue
    gross_profit = effective_revenue - cogs
    total_expenses = sum(expenses.values())
    marginal_profit = gross_profit - total_expenses
    loan_finance_cost = loan_interest + loan_fee
    profit_before_tax = marginal_profit - loan_finance_cost
    # База налога — effective_revenue (после возвратов). calc_tax сам выбирает
    # выручку vs прибыль в зависимости от режима.
    tax = calc_tax(
        revenue=effective_revenue,
        gross_profit=profit_before_tax,
        tax_regime=tax_regime,
        tax_rate_pct=tax_rate_pct,
        vat_rate_pct=vat_rate_pct,
    )
    return PnLResult(
        seller_revenue=seller_revenue,
        buyer_revenue=buyer_revenue,
        spp_compensation=seller_revenue - buyer_revenue,
        returned_revenue=returned_revenue,
        effective_revenue=effective_revenue,
        cogs=cogs,
        gross_profit=gross_profit,
        total_expenses=total_expenses,
        marginal_profit=marginal_profit,
        loan_finance_cost=loan_finance_cost,
        profit_before_tax=profit_before_tax,
        tax=tax,
    )
