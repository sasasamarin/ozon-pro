"""
/api/v1/loans/cashflow-impact — влияние кредитов на cashflow.

Сравнивает план платежей по кредитам с прогнозом cashflow:
  - DSCR (debt service coverage ratio) = операционный cashflow / платежи
  - месяцы с риском (DSCR < 1)
  - доля кредитной нагрузки в outflow
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, UTC

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.deps_cabinets import get_accessible_cabinet_ids
from app.db.session import get_db
from app.models import User, OzonAccount, Transaction
from app.models.loan import Loan, LoanPayment


router = APIRouter()


class MonthImpact(BaseModel):
    month: str           # 'YYYY-MM'
    loan_payment_rub: float       # тело+проценты+комиссии за месяц
    historical_net_cashflow_rub: float  # net за тот же месяц годом ранее (proxy)
    dscr: float | None   # net / loan_payment (если payment=0 → None)
    risk: str            # 'safe' / 'tight' / 'overload'


class CashflowImpactResp(BaseModel):
    horizon_months: int
    items: list[MonthImpact]
    summary: dict


@router.get("/cashflow-impact", response_model=CashflowImpactResp)
async def cashflow_impact(
    horizon_months: int = Query(12, ge=3, le=36),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CashflowImpactResp:
    today = date.today()

    # 1) План платежей по кредитам помесячно — вперёд на horizon
    end_date = date(today.year + (today.month + horizon_months - 1) // 12,
                    ((today.month + horizon_months - 1) % 12) + 1, 1)
    plan_rows = (await db.execute(
        select(LoanPayment)
        .join(Loan, Loan.id == LoanPayment.loan_id)
        .where(
            LoanPayment.company_id == current_user.company_id,
            LoanPayment.pay_date >= today,
            LoanPayment.pay_date < end_date,
            LoanPayment.is_paid == False,
        )
    )).scalars().all()

    plan_by_month: dict[str, float] = defaultdict(float)
    for p in plan_rows:
        k = f"{p.pay_date.year:04d}-{p.pay_date.month:02d}"
        plan_by_month[k] += float(p.principal_part or 0) + float(p.interest_part or 0) + float(p.fee_part or 0)

    # 2) Исторический net cashflow по месяцам — те же месяцы годом ранее (proxy)
    hist_from = datetime(today.year - 1, today.month, 1, tzinfo=UTC)
    hist_to = hist_from + timedelta(days=horizon_months * 31 + 31)

    accessible = await get_accessible_cabinet_ids(db, current_user)
    accs_q = select(OzonAccount.id).where(
        OzonAccount.company_id == current_user.company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if accessible is not None:
        accs_q = accs_q.where(OzonAccount.id.in_(accessible))
    accs = [r[0] for r in (await db.execute(accs_q)).all()]

    hist_by_month: dict[str, float] = defaultdict(float)
    if accs:
        bucket = func.date_trunc("month", Transaction.time).label("bucket")
        inflow_expr = func.coalesce(
            func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)), 0
        ).label("inflow")
        outflow_expr = func.coalesce(
            func.sum(case((Transaction.amount < 0, -Transaction.amount), else_=0)), 0
        ).label("outflow")
        rows = (await db.execute(
            select(bucket, inflow_expr, outflow_expr)
            .where(
                Transaction.ozon_account_id.in_(accs),
                Transaction.time >= hist_from,
                Transaction.time < hist_to,
            )
            .group_by(bucket).order_by(bucket)
        )).all()
        for r in rows:
            # Маппим прошлогодний месяц на текущий горизонт
            d = r.bucket.date()
            try:
                proj = date(d.year + 1, d.month, 1)
            except ValueError:
                continue
            k = f"{proj.year:04d}-{proj.month:02d}"
            hist_by_month[k] += float(r.inflow or 0) - float(r.outflow or 0)

    # 3) Сводим
    months_iter = []
    y, m = today.year, today.month
    for _ in range(horizon_months):
        months_iter.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1; y += 1

    items: list[MonthImpact] = []
    risk_counts = {"safe": 0, "tight": 0, "overload": 0}
    total_payments = 0.0
    total_hist_net = 0.0

    for mk in months_iter:
        pay = plan_by_month.get(mk, 0)
        hist = hist_by_month.get(mk, 0)
        dscr: float | None = None
        if pay > 0:
            dscr = round(hist / pay, 2) if hist else 0
        # Риск-метка
        if pay == 0:
            risk = "safe"
        elif hist <= 0:
            risk = "overload"
        elif dscr is not None and dscr < 1:
            risk = "overload"
        elif dscr is not None and dscr < 1.5:
            risk = "tight"
        else:
            risk = "safe"
        risk_counts[risk] += 1
        total_payments += pay
        total_hist_net += hist

        items.append(MonthImpact(
            month=mk,
            loan_payment_rub=round(pay, 2),
            historical_net_cashflow_rub=round(hist, 2),
            dscr=dscr,
            risk=risk,
        ))

    avg_dscr = round(total_hist_net / total_payments, 2) if total_payments > 0 else None

    return CashflowImpactResp(
        horizon_months=horizon_months,
        items=items,
        summary={
            "total_loan_payments_rub": round(total_payments, 2),
            "total_hist_net_rub": round(total_hist_net, 2),
            "avg_dscr": avg_dscr,
            "months_at_risk": risk_counts["overload"] + risk_counts["tight"],
            "months_overload": risk_counts["overload"],
            "months_safe": risk_counts["safe"],
            "note": (
                "DSCR = чистый cashflow / платёж по кредиту. "
                "Прогноз — proxy на основе того же месяца годом ранее. "
                "DSCR ≥ 1.5 = безопасно; 1-1.5 = напряжённо; < 1 = перегрузка."
            ),
        },
    )
