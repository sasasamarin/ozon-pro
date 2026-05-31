"""
Юнит-калькулятор — backend endpoint.

POST /api/v1/products/calculator/calc

Раньше расчёт жил в Calculator.tsx, причём налог считался как
`tax_amount = price * tax_rate / 100` — это правильно ТОЛЬКО для УСН Доходы.
Для УСН Доходы-Расходы и ОСНО база налога — прибыль, не цена.
Перенесли на backend и используем общий services.tax.calc_tax.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Company, User
from app.services.tax import calc_tax

router = APIRouter()


class CalcInput(BaseModel):
    price: float = Field(..., ge=0, description="Цена продажи ₽")
    cost: float = Field(..., ge=0, description="Себестоимость ₽")
    commission_pct: float = Field(..., ge=0, le=100, description="Комиссия Ozon %")
    logistics: float = Field(..., ge=0)
    ad_spend: float = Field(..., ge=0)
    packaging: float = Field(0, ge=0)
    # Опциональный override налога — если юзер хочет посмотреть «что если ОСНО»
    tax_regime: str | None = None
    tax_rate_pct: float | None = None


class CalcResult(BaseModel):
    # Раскладка по статьям (в рублях)
    commission_amount: float
    gross_margin: float          # цена − себест − комиссия − логистика − упаковка
    op_profit: float             # gross_margin − реклама (= прибыль до налога)
    tax_amount: float            # из calc_tax
    vat_amount: float
    net_margin: float            # чистая прибыль после налога
    # KPI
    margin_pct: float            # net_margin / price * 100
    roi_pct: float | None        # net_margin / cost * 100 (None если cost=0)
    breakeven_price: float       # цена при которой net_margin = 0
    # Метаданные для UI
    tax_regime: str
    tax_regime_label: str
    tax_rate_pct: float
    tax_base_label: str          # «выручка» / «прибыль» / «без налога»


def _net_profit_at_price(
    price: float, inp: CalcInput, regime: str, rate: float, vat_rate: float | None
) -> float:
    """Вспомогательная функция для bisection при поиске breakeven."""
    comm = price * inp.commission_pct / 100
    gm = price - inp.cost - comm - inp.logistics - inp.packaging
    op = gm - inp.ad_spend
    res = calc_tax(
        revenue=price,
        gross_profit=op,
        tax_regime=regime,
        tax_rate_pct=rate,
        vat_rate_pct=vat_rate,
    )
    return res.net_profit


def _find_breakeven(
    inp: CalcInput, regime: str, rate: float, vat_rate: float | None
) -> float:
    """
    Численный поиск точки безубыточности (net_profit == 0) через bisection.
    Работает для любого налогового режима, в отличие от закрытой формулы.
    Возвращает 0 если безубыточность не достижима в разумном диапазоне.
    """
    lo, hi = 0.0, max(inp.cost * 50, inp.price * 10, 100_000.0)
    # Если даже на верхней границе убыток — безубыточность недостижима
    if _net_profit_at_price(hi, inp, regime, rate, vat_rate) < 0:
        return 0.0
    # Если на цене 0 уже плюс — тоже странно, возвращаем 0
    if _net_profit_at_price(lo, inp, regime, rate, vat_rate) > 0:
        return 0.0
    for _ in range(60):  # точность ~ hi / 2^60, заведомо < копейки
        mid = (lo + hi) / 2
        np = _net_profit_at_price(mid, inp, regime, rate, vat_rate)
        if np < 0:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 2)


@router.post("/calc", response_model=CalcResult)
async def calculate(
    inp: CalcInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CalcResult:
    # Tax settings — из компании, если не переопределили в запросе
    company = (await db.execute(select(Company).where(Company.id == current_user.company_id))).scalar_one()
    regime = inp.tax_regime or company.tax_regime or "none"
    rate = inp.tax_rate_pct if inp.tax_rate_pct is not None else (company.tax_rate_pct or 0)
    vat_rate = company.vat_rate_pct  # НДС всегда из настроек, не из инпута калька

    comm_amount = inp.price * inp.commission_pct / 100
    gross_margin = inp.price - inp.cost - comm_amount - inp.logistics - inp.packaging
    op_profit = gross_margin - inp.ad_spend

    tax_res = calc_tax(
        revenue=inp.price,
        gross_profit=op_profit,
        tax_regime=regime,
        tax_rate_pct=float(rate),
        vat_rate_pct=float(vat_rate) if vat_rate is not None else None,
    )

    margin_pct = (tax_res.net_profit / inp.price * 100) if inp.price > 0 else 0.0
    roi_pct = (tax_res.net_profit / inp.cost * 100) if inp.cost > 0 else None
    breakeven = _find_breakeven(inp, regime, float(rate), float(vat_rate) if vat_rate else None)

    return CalcResult(
        commission_amount=round(comm_amount, 2),
        gross_margin=round(gross_margin, 2),
        op_profit=round(op_profit, 2),
        tax_amount=tax_res.tax_amount,
        vat_amount=tax_res.vat_amount,
        net_margin=tax_res.net_profit,
        margin_pct=round(margin_pct, 2),
        roi_pct=round(roi_pct, 2) if roi_pct is not None else None,
        breakeven_price=breakeven,
        tax_regime=tax_res.regime,
        tax_regime_label=tax_res.regime_label,
        tax_rate_pct=tax_res.rate_pct,
        tax_base_label=tax_res.base_label,
    )
