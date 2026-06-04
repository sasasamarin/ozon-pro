"""
/api/v1/taxes — налоговый расчёт для UI «Налоги».

Берёт revenue + gross_profit за период (как в pnl.py), применяет
calc_tax из services/tax.py с настройками компании.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Company, User
from app.services.tax import calc_tax


router = APIRouter()


class TaxResp(BaseModel):
    period_from: str
    period_to: str
    regime: str
    regime_label: str
    rate_pct: float
    vat_rate_pct: float | None
    revenue: float
    expenses: float
    gross_profit: float
    tax_amount: float
    vat_amount: float
    net_profit_after_tax: float
    monthly_breakdown: list[dict]
    note: str


@router.get("/", response_model=TaxResp)
async def taxes(
    days: int = Query(30, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaxResp:
    """Расчёт налога за период по настройкам компании."""
    company = (await db.execute(
        text("SELECT * FROM companies WHERE id = :cid"),
        {"cid": str(current_user.company_id)},
    )).first()
    if not company:
        raise HTTPException(404, "Компания не найдена")

    regime = getattr(company, 'tax_regime', None) or 'usn_income'
    rate = float(getattr(company, 'tax_rate_pct', 0) or 6)
    vat_rate = float(getattr(company, 'vat_rate_pct', 0) or 0) or None

    df = date.today() - timedelta(days=days)

    # Revenue + расходы (как в pnl.py — operational контур)
    r = (await db.execute(text("""
        SELECT
            COALESCE(SUM(t.accruals_for_sale) FILTER (WHERE t.operation_type='OperationAgentDeliveredToCustomer'), 0)::float AS revenue,
            COALESCE(SUM(ABS(t.sale_commission)), 0)::float AS commissions,
            COALESCE(SUM(ABS(t.delivery_to_customer)), 0)::float AS logistics,
            COALESCE(SUM(ABS(t.storage)), 0)::float AS storage,
            COALESCE(SUM(ABS(t.acquiring)), 0)::float AS acquiring,
            COALESCE(SUM(ABS(t.advertising)), 0)::float AS advertising,
            COALESCE(SUM(ABS(t.last_mile)), 0)::float AS last_mile,
            COALESCE(SUM(ABS(t.return_logistics)), 0)::float AS return_logistics
        FROM transactions t
        JOIN ozon_accounts oa ON oa.id = t.ozon_account_id
        WHERE oa.company_id = :cid AND t.operation_date >= :df
    """), {"cid": str(current_user.company_id), "df": df})).first()

    revenue = float(r.revenue or 0)
    expenses = sum(float(getattr(r, c) or 0) for c in (
        "commissions", "logistics", "storage", "acquiring",
        "advertising", "last_mile", "return_logistics",
    ))
    gross = revenue - expenses

    result = calc_tax(
        revenue=revenue, gross_profit=gross,
        tax_regime=regime, tax_rate_pct=rate, vat_rate_pct=vat_rate,
    )

    # Помесячная разбивка
    monthly = (await db.execute(text("""
        SELECT date_trunc('month', t.operation_date)::date AS month,
               COALESCE(SUM(t.accruals_for_sale) FILTER (WHERE t.operation_type='OperationAgentDeliveredToCustomer'), 0)::float AS rev
        FROM transactions t
        JOIN ozon_accounts oa ON oa.id = t.ozon_account_id
        WHERE oa.company_id = :cid AND t.operation_date >= :df
        GROUP BY 1 ORDER BY 1
    """), {"cid": str(current_user.company_id), "df": df})).all()

    monthly_breakdown = []
    for row in monthly:
        m_rev = float(row.rev or 0)
        # Простой пропорциональный расчёт налога per month
        m_tax = m_rev * (rate / 100) if regime == "usn_income" else (result.tax_amount * (m_rev / revenue) if revenue else 0)
        monthly_breakdown.append({
            "month": row.month.isoformat()[:7],
            "revenue": round(m_rev, 2),
            "tax_estimate": round(m_tax, 2),
        })

    return TaxResp(
        period_from=df.isoformat(), period_to=date.today().isoformat(),
        regime=result.regime, regime_label=result.regime_label,
        rate_pct=result.rate_pct, vat_rate_pct=vat_rate,
        revenue=round(revenue, 2),
        expenses=round(expenses, 2),
        gross_profit=round(gross, 2),
        tax_amount=round(result.tax_amount, 2),
        vat_amount=round(result.vat_amount, 2),
        net_profit_after_tax=round(result.net_profit, 2),
        monthly_breakdown=monthly_breakdown,
        note=(
            f"Режим: {result.regime_label}. Базы для расчёта: {result.base_label}. "
            f"Источник revenue — Transaction.accruals_for_sale (оперативная модель)."
        ),
    )
