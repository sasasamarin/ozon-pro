"""
Golden-тесты формулы P&L (services/pnl_compute.py).

Фиксируют инварианты CLAUDE.md «Формула P&L» (выверено на Crema Viva, diff=0),
чтобы выручка/прибыль больше не разъезжались при будущих правках:

  - Баллы за скидки — ПРИТОК (входят в seller_revenue, НЕ вычитаются);
  - тело займа в P&L НЕ попадает (только проценты + комиссии);
  - чистая прибыль = до налога − налог;
  - база налога — effective_revenue (после возвратов).
"""
from __future__ import annotations

import pytest

from app.services.pnl_compute import compute_pnl


def test_full_chain_usn_income_6pct():
    """Полная цепочка P&L на контролируемых числах (УСН Доходы 6%)."""
    r = compute_pnl(
        seller_revenue=1_000_000,
        buyer_revenue=880_000,
        returned_revenue=100_000,
        cogs=200_000,
        expenses={"Комиссия Ozon": 300_000, "Логистика": 50_000},
        loan_interest=20_000,
        loan_fee=5_000,
        tax_regime="usn_income",
        tax_rate_pct=6.0,
    )
    assert r.effective_revenue == pytest.approx(900_000)      # 1M − возвраты 100k
    assert r.gross_profit == pytest.approx(700_000)           # 900k − cogs 200k
    assert r.total_expenses == pytest.approx(350_000)
    assert r.marginal_profit == pytest.approx(350_000)        # 700k − 350k
    assert r.loan_finance_cost == pytest.approx(25_000)       # % 20k + комиссия 5k
    assert r.profit_before_tax == pytest.approx(325_000)      # 350k − 25k
    # УСН Доходы: налог = 6% от effective_revenue (900k), НЕ от прибыли
    assert r.tax.tax_amount == pytest.approx(54_000)
    assert r.tax.net_profit == pytest.approx(271_000)         # 325k − 54k
    assert r.spp_compensation == pytest.approx(120_000)       # seller − buyer


def test_discount_points_are_inflow_not_expense():
    """Баллы за скидки — ПРИТОК: входят в seller_revenue и не вычитаются.

    Опровергнутый миф «СПП = баллы / баллы — расход» (CLAUDE.md). Если в
    будущем кто-то начнёт вычитать баллы, эта проверка упадёт.
    """
    base = compute_pnl(seller_revenue=1_000_000, cogs=0, expenses={})
    # +50k Баллов за скидки уже сидят в accruals_for_sale → выручка выше на 50k
    with_points = compute_pnl(seller_revenue=1_050_000, cogs=0, expenses={})
    delta = with_points.marginal_profit - base.marginal_profit
    assert delta == pytest.approx(50_000)  # приток дошёл до прибыли 1:1, не срезан


def test_loan_principal_never_in_pnl():
    """Тело займа в P&L не существует как параметр — попасть туда не может.

    Уменьшают прибыль ТОЛЬКО проценты и комиссии (CLAUDE.md, flowoi_tz_loans).
    """
    no_loan = compute_pnl(seller_revenue=500_000, cogs=100_000, expenses={"x": 50_000})
    with_loan = compute_pnl(
        seller_revenue=500_000, cogs=100_000, expenses={"x": 50_000},
        loan_interest=30_000, loan_fee=10_000,
    )
    # Разница = ровно проценты+комиссии (40k), без какого-либо «тела».
    assert no_loan.profit_before_tax - with_loan.profit_before_tax == pytest.approx(40_000)
    assert with_loan.marginal_profit == no_loan.marginal_profit  # маржа выше займов не трогается


def test_tax_base_is_effective_revenue_after_returns():
    """База УСН Доходы — выручка ПОСЛЕ возвратов (effective_revenue)."""
    r = compute_pnl(
        seller_revenue=1_000_000, returned_revenue=200_000,
        cogs=0, expenses={}, tax_regime="usn_income", tax_rate_pct=6.0,
    )
    assert r.effective_revenue == pytest.approx(800_000)
    assert r.tax.tax_amount == pytest.approx(48_000)  # 6% от 800k, не от 1M


def test_usn_income_minus_15pct_on_profit():
    """УСН Доходы−Расходы: 15% от прибыли до налога."""
    r = compute_pnl(
        seller_revenue=1_000_000, cogs=200_000,
        expenses={"Комиссия": 300_000},
        tax_regime="usn_income_minus", tax_rate_pct=15.0,
    )
    assert r.marginal_profit == pytest.approx(500_000)
    assert r.profit_before_tax == pytest.approx(500_000)
    assert r.tax.tax_amount == pytest.approx(75_000)   # 15% × 500k (> мин 1% × 1M)
    assert r.tax.net_profit == pytest.approx(425_000)


def test_empty_inputs_are_zero():
    """Пустой период не падает и даёт нули."""
    r = compute_pnl(seller_revenue=0)
    assert r.marginal_profit == 0
    assert r.tax.net_profit == 0
