"""
/api/v1/loans/schedule — общий график платежей по всем кредитам компании.

LoanPayment-ы строятся через services/loan_schedule.py при создании
Loan. Этот endpoint их просто читает + строит timeline (помесячно).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.models.loan import Loan, LoanPayment


router = APIRouter()


class PaymentRow(BaseModel):
    payment_id: str
    loan_id: str
    lender: str | None
    seq: int
    pay_date: str
    principal_part: float
    interest_part: float
    fee_part: float
    total: float
    is_paid: bool
    overdue_days: int  # сколько дней просрочки (0 если не просрочен)


class MonthAggregate(BaseModel):
    month: str          # 'YYYY-MM'
    total_due: float
    principal: float
    interest: float
    fee: float
    payments_count: int
    paid_count: int


class ScheduleResp(BaseModel):
    items: list[PaymentRow]
    by_month: list[MonthAggregate]
    summary: dict


@router.get("/schedule", response_model=ScheduleResp)
async def loans_schedule(
    only_unpaid: bool = Query(False),
    days_ahead: int = Query(365, ge=30, le=3650),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScheduleResp:
    """График платежей: все LoanPayment-ы компании + помесячная агрегация."""
    rows = (await db.execute(
        select(LoanPayment, Loan.lender)
        .join(Loan, Loan.id == LoanPayment.loan_id)
        .where(LoanPayment.company_id == current_user.company_id)
        .order_by(LoanPayment.pay_date)
    )).all()

    today = date.today()
    items: list[PaymentRow] = []
    by_month: dict[str, dict] = defaultdict(lambda: {
        "total": 0.0, "principal": 0.0, "interest": 0.0, "fee": 0.0,
        "count": 0, "paid": 0,
    })

    total_due = total_paid = 0.0
    overdue_count = 0

    for p, lender in rows:
        if only_unpaid and p.is_paid:
            continue
        total = float(p.principal_part or 0) + float(p.interest_part or 0) + float(p.fee_part or 0)
        overdue = 0
        if not p.is_paid and p.pay_date < today:
            overdue = (today - p.pay_date).days
            overdue_count += 1

        items.append(PaymentRow(
            payment_id=str(p.id), loan_id=str(p.loan_id),
            lender=lender, seq=p.seq,
            pay_date=p.pay_date.isoformat(),
            principal_part=float(p.principal_part or 0),
            interest_part=float(p.interest_part or 0),
            fee_part=float(p.fee_part or 0),
            total=round(total, 2),
            is_paid=p.is_paid,
            overdue_days=overdue,
        ))

        m_key = f"{p.pay_date.year:04d}-{p.pay_date.month:02d}"
        b = by_month[m_key]
        b["total"] += total
        b["principal"] += float(p.principal_part or 0)
        b["interest"] += float(p.interest_part or 0)
        b["fee"] += float(p.fee_part or 0)
        b["count"] += 1
        if p.is_paid:
            b["paid"] += 1
            total_paid += total
        else:
            total_due += total

    months_sorted = sorted(by_month.keys())
    by_month_list = [
        MonthAggregate(
            month=m,
            total_due=round(by_month[m]["total"], 2),
            principal=round(by_month[m]["principal"], 2),
            interest=round(by_month[m]["interest"], 2),
            fee=round(by_month[m]["fee"], 2),
            payments_count=by_month[m]["count"],
            paid_count=by_month[m]["paid"],
        )
        for m in months_sorted
    ]

    # Ближайший платёж
    next_payment = None
    for r in items:
        if not r.is_paid and r.pay_date >= today.isoformat():
            next_payment = r
            break

    return ScheduleResp(
        items=items,
        by_month=by_month_list,
        summary={
            "total_payments": len(items),
            "overdue_count": overdue_count,
            "total_due_rub": round(total_due, 2),
            "total_paid_rub": round(total_paid, 2),
            "next_payment_date": next_payment.pay_date if next_payment else None,
            "next_payment_amount_rub": next_payment.total if next_payment else None,
            "next_payment_lender": next_payment.lender if next_payment else None,
        },
    )
