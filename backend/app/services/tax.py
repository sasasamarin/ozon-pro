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
    vat_amount: float           # НДС, который мы платим (с выручки)
    vat_refundable: bool        # возвратный (ОСНО) или нет (УСН с НДС 5%/7%)
    net_profit: float           # к выплате после налога и НДС


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
    vat_refundable: bool = False,
) -> TaxResult:
    """
    revenue       — выручка продавца (= seller_price × qty доставленных)
    gross_profit  — прибыль ДО налога (= revenue − cost − комиссия − реклама − логистика − эквайринг)
    vat_rate_pct  — ставка НДС (5/7/22). Применяется к любому режиму, не только ОСНО.
                    С 2025 года УСН с доходом >60млн обязан платить НДС 5% или 7%.
    vat_refundable — True для ОСНО (входной НДС вычитается),
                     False для УСН-с-НДС (входной НДС не возвращается, фактически расход).

    Возвращает структуру с разбивкой налога и НДС, и чистую прибыль ПОСЛЕ всего.
    """
    label = _label(tax_regime)
    vat = revenue * (vat_rate_pct / 100) if vat_rate_pct else 0.0

    if tax_regime == "usn_income":
        # % от выручки. База — БЕЗ НДС (НДС в выручке выделяется отдельно).
        base_revenue = revenue - vat if vat_refundable else revenue
        tax = base_revenue * (tax_rate_pct / 100)
        base = "выручка" + (" без НДС" if vat_refundable else "")
    elif tax_regime == "usn_income_minus":
        # % от прибыли (но не меньше 1% от выручки)
        tax_from_profit = max(gross_profit, 0) * (tax_rate_pct / 100)
        min_tax = revenue * 0.01
        tax = max(tax_from_profit, min_tax)
        base = "прибыль (мин. 1% от выручки)"
    elif tax_regime == "osno":
        # 20% от прибыли. Если НДС возвратный — он не вычитается из прибыли
        # (это НДС с продаж минус входной НДС, к доплате в бюджет).
        # Если невозвратный — фактически расход, уменьшает прибыль.
        profit_taxable = max(gross_profit - (0 if vat_refundable else vat), 0)
        tax = profit_taxable * (tax_rate_pct / 100)
        base = "прибыль" + (" (НДС возвратный)" if vat_refundable else " (после невозвратного НДС)")
    else:
        tax = 0.0
        base = "без налога"

    # Чистая прибыль: gross − tax. Если НДС невозвратный — вычитаем ещё его.
    # Если возвратный — он не уменьшает прибыль (вернётся вычетом).
    net = gross_profit - tax - (0 if vat_refundable else vat)

    return TaxResult(
        regime=tax_regime,
        regime_label=label,
        rate_pct=tax_rate_pct,
        base_label=base,
        tax_amount=round(tax, 2),
        vat_amount=round(vat, 2),
        vat_refundable=vat_refundable,
        net_profit=round(net, 2),
    )


# ============================================
# Helper: получить настройки налога для кабинета
# ============================================

def get_cabinet_tax(cabinet: object | None, company: object | None) -> dict:
    """
    Возвращает actual налоговые настройки для кабинета.

    Каждое поле: cabinet.X если задано (не None), иначе company.X.
    Это позволяет иметь default по компании + переопределения per-cabinet.
    """
    def pick(field: str, default):
        if cabinet is not None:
            v = getattr(cabinet, field, None)
            if v is not None:
                return v
        if company is not None:
            v = getattr(company, field, None)
            if v is not None:
                return v
        return default

    return {
        "tax_regime": pick("tax_regime", "usn_income"),
        "tax_rate_pct": float(pick("tax_rate_pct", 6) or 6),
        "vat_rate_pct": (
            float(getattr(cabinet, "vat_rate_pct", None))
            if cabinet is not None and getattr(cabinet, "vat_rate_pct", None) is not None
            else (float(getattr(company, "vat_rate_pct", None))
                  if company is not None and getattr(company, "vat_rate_pct", None) is not None
                  else None)
        ),
        "vat_refundable": bool(
            getattr(cabinet, "vat_refundable", False) if cabinet is not None else False
        ),
        "tax_region_note": (
            getattr(cabinet, "tax_region_note", None) if cabinet is not None else None
        ),
    }
