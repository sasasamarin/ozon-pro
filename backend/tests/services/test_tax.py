"""Тесты налогового расчёта — фундамент P&L и WhatIf."""
from __future__ import annotations

import pytest
from app.services.tax import calc_tax


def test_usn_income_6pct():
    """УСН Доходы: налог = 6% от выручки, прибыль игнорируется."""
    r = calc_tax(revenue=1_000_000, gross_profit=300_000,
                 tax_regime="usn_income", tax_rate_pct=6.0)
    assert r.tax_amount == pytest.approx(60_000)
    assert r.vat_amount == 0
    assert r.net_profit == pytest.approx(240_000)
    assert r.base_label == "выручка"


def test_usn_income_no_profit_still_pays():
    """УСН Доходы платится даже при нуле прибыли — раздражающая особенность УСН."""
    r = calc_tax(revenue=500_000, gross_profit=0,
                 tax_regime="usn_income", tax_rate_pct=6.0)
    assert r.tax_amount == pytest.approx(30_000)
    assert r.net_profit == pytest.approx(-30_000)  # минус — норма для УСН Доходы при нулевой прибыли


def test_usn_income_minus_uses_profit():
    """УСН Дох-Расх: 15% от прибыли."""
    r = calc_tax(revenue=1_000_000, gross_profit=300_000,
                 tax_regime="usn_income_minus", tax_rate_pct=15.0)
    assert r.tax_amount == pytest.approx(45_000)
    assert r.net_profit == pytest.approx(255_000)


def test_usn_income_minus_minimum_tax():
    """Минимальный налог УСН Дох-Расх — 1% от выручки при низкой прибыли."""
    r = calc_tax(revenue=1_000_000, gross_profit=10_000,  # 15% × 10k = 1.5k, но мин 1% × 1M = 10k
                 tax_regime="usn_income_minus", tax_rate_pct=15.0)
    assert r.tax_amount == pytest.approx(10_000)  # минимальный сработал


def test_usn_income_minus_negative_profit():
    """Убыток + УСН Дох-Расх: всё равно минимальный налог 1%."""
    r = calc_tax(revenue=500_000, gross_profit=-100_000,
                 tax_regime="usn_income_minus", tax_rate_pct=15.0)
    assert r.tax_amount == pytest.approx(5_000)  # 1% от выручки


def test_osno_with_vat():
    """ОСНО: 20% от прибыли (после вычета НДС) + НДС 20% с выручки."""
    r = calc_tax(revenue=1_000_000, gross_profit=400_000,
                 tax_regime="osno", tax_rate_pct=20.0, vat_rate_pct=20.0)
    assert r.vat_amount == pytest.approx(200_000)
    # 400k − 200k VAT = 200k налогооблагаемая → 20% = 40k
    assert r.tax_amount == pytest.approx(40_000)
    assert r.net_profit == pytest.approx(400_000 - 40_000 - 200_000)


def test_none_regime():
    """Без налога — net == gross."""
    r = calc_tax(revenue=1_000_000, gross_profit=300_000,
                 tax_regime="none", tax_rate_pct=0)
    assert r.tax_amount == 0
    assert r.net_profit == 300_000


def test_zero_revenue():
    """Краевой: 0 выручки."""
    r = calc_tax(revenue=0, gross_profit=0,
                 tax_regime="usn_income", tax_rate_pct=6.0)
    assert r.tax_amount == 0
    assert r.net_profit == 0
