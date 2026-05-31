"""
Расчёт налога на основе настроек компании.

Используется везде где считается «чистая прибыль»:
- /finance/pnl
- /finance/cashflow
- Экономика продаж (per-product P&L)
- юнит-калькулятор
- what-if симулятор

Принцип: gross_profit_before_tax → tax(regime, rate) → net_profit_after_tax
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TaxResult:
    regime: str
    regime_label: str
    rate_pct: float
    base_label: str             # «выручка» / «прибыль» / «без налога»
    tax_amount: float           # сколько забирает налог
    vat_amount: float           # НДС с выручки (если ОСНО)
    net_profit: float           # к выплате после налога


def _label(regime: str) -> str:
    return {
        "usn_income":        "УСН Доходы",
        "usn_income_minus":  "УСН Доходы-Расходы",
        "osno":              "ОСНО",
        "none":              "Без налога",
    }.get(regime, regime)


def calc_tax(
    *,
    revenue: float,
    gross_profit: float,
    tax_regime: str,
    tax_rate_pct: float,
    vat_rate_pct: float | None = None,
) -> TaxResult:
    """
    revenue       — выручка продавца (= seller_price × qty доставленных)
    gross_profit  — прибыль ДО налога (= revenue − cost − комиссия − реклама − логистика − эквайринг)

    Возвращает структуру с разбивкой налога и НДС, и чистую прибыль ПОСЛЕ налога.
    """
    label = _label(tax_regime)
    vat = 0.0
    if tax_regime == "osno" and vat_rate_pct:
        # НДС с выручки (упрощённо — не учитывая входной НДС)
        vat = revenue * (vat_rate_pct / 100)

    if tax_regime == "usn_income":
        # % от выручки
        tax = revenue * (tax_rate_pct / 100)
        base = "выручка"
    elif tax_regime == "usn_income_minus":
        # % от прибыли (но не меньше 1% от выручки — минимальный налог УСН)
        tax_from_profit = max(gross_profit, 0) * (tax_rate_pct / 100)
        min_tax = revenue * 0.01
        tax = max(tax_from_profit, min_tax)
        base = "прибыль (мин. 1% от выручки)"
    elif tax_regime == "osno":
        # 20% от прибыли (после НДС)
        profit_after_vat = max(gross_profit - vat, 0)
        tax = profit_after_vat * (tax_rate_pct / 100)
        base = "прибыль (после НДС)"
    else:
        tax = 0.0
        base = "без налога"

    net = gross_profit - tax - vat

    return TaxResult(
        regime=tax_regime,
        regime_label=label,
        rate_pct=tax_rate_pct,
        base_label=base,
        tax_amount=round(tax, 2),
        vat_amount=round(vat, 2),
        net_profit=round(net, 2),
    )
