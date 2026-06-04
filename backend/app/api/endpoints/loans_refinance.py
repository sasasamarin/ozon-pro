"""
/api/v1/loans/refinance — калькулятор рефинансирования.

Берёт список активных Loan, считает их аннуитет на оставшийся срок,
сравнивает с новой ставкой/сроком из payload.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.models.loan import Loan, LoanPayment


router = APIRouter()


class RefinanceInput(BaseModel):
    loan_id: str | None = None     # None = все активные кредиты вместе
    new_rate_pct: float            # годовая ставка нового кредита (%)
    new_term_months: int           # срок нового кредита
    early_repayment_fee_rub: float = 0  # штраф за досрочное погашение текущих


class LoanCmp(BaseModel):
    loan_id: str
    lender: str | None
    current_remaining_principal: float
    current_rate_pct: float
    current_payments_left: int
    current_remaining_payments_sum: float
    current_remaining_interest: float


class RefinanceResp(BaseModel):
    current: list[LoanCmp]
    current_total_remaining: float
    current_total_payments_left_sum: float
    current_total_interest_left: float
    new_principal: float
    new_monthly_payment: float
    new_total_payments_sum: float
    new_total_interest: float
    savings_rub: float        # положительное = выгодно рефинансировать
    savings_pct: float
    recommendation: str
    breakeven_months: int | None
    note: str


def _annuity(principal: float, annual_rate_pct: float, term_months: int) -> float:
    if term_months <= 0:
        return 0.0
    if annual_rate_pct <= 0:
        return principal / term_months
    m = annual_rate_pct / 100 / 12
    return principal * m * (1 + m) ** term_months / ((1 + m) ** term_months - 1)


@router.post("/refinance", response_model=RefinanceResp)
async def refinance_calc(
    payload: RefinanceInput = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RefinanceResp:
    """Калькулятор: сравнить текущие кредиты с одним новым."""
    q = select(Loan).where(
        Loan.company_id == current_user.company_id,
        Loan.status == "active",
    )
    if payload.loan_id:
        try:
            import uuid as _u
            lid = _u.UUID(payload.loan_id)
            q = q.where(Loan.id == lid)
        except ValueError:
            raise HTTPException(400, "Невалидный loan_id")

    loans = (await db.execute(q)).scalars().all()
    if not loans:
        raise HTTPException(404, "Нет активных кредитов для рефинансирования")

    # Для каждого: считаем оставшийся принципал из неоплаченных LoanPayment-ов
    items: list[LoanCmp] = []
    total_remaining = 0.0
    total_payments_left = 0.0
    total_interest_left = 0.0

    for loan in loans:
        pays = (await db.execute(
            select(LoanPayment).where(
                LoanPayment.loan_id == loan.id,
                LoanPayment.is_paid == False,
            )
        )).scalars().all()
        remaining_p = sum(float(p.principal_part or 0) for p in pays)
        remaining_i = sum(float(p.interest_part or 0) for p in pays)
        remaining_f = sum(float(p.fee_part or 0) for p in pays)
        payments_left = len(pays)
        sum_left = remaining_p + remaining_i + remaining_f

        items.append(LoanCmp(
            loan_id=str(loan.id),
            lender=loan.lender,
            current_remaining_principal=round(remaining_p, 2),
            current_rate_pct=float(loan.rate_pct or 0),
            current_payments_left=payments_left,
            current_remaining_payments_sum=round(sum_left, 2),
            current_remaining_interest=round(remaining_i + remaining_f, 2),
        ))
        total_remaining += remaining_p
        total_payments_left += sum_left
        total_interest_left += remaining_i + remaining_f

    # Новый кредит покрывает весь оставшийся принципал + штрафы
    new_principal = total_remaining + payload.early_repayment_fee_rub
    new_monthly = _annuity(new_principal, payload.new_rate_pct, payload.new_term_months)
    new_total = new_monthly * payload.new_term_months
    new_interest = new_total - new_principal

    savings = total_payments_left - new_total
    savings_pct = (savings / total_payments_left * 100) if total_payments_left else 0

    # Точка безубыточности по месяцам: после скольких месяцев экономия
    # перекроет штраф за досрочку
    breakeven = None
    if payload.early_repayment_fee_rub > 0 and savings > 0:
        # экономия в месяц (примерно) = (total_payments_left/avg_months_left) - new_monthly
        avg_left = max(1, max(i.current_payments_left for i in items))
        cur_monthly = total_payments_left / avg_left
        monthly_save = cur_monthly - new_monthly
        if monthly_save > 0:
            breakeven = int(payload.early_repayment_fee_rub / monthly_save) + 1

    if savings > 50000:
        rec = "Рефинансировать выгодно"
    elif savings > 0:
        rec = "Можно рефинансировать, экономия небольшая"
    elif savings > -50000:
        rec = "Разница незначительна — оставить как есть"
    else:
        rec = "Рефинансирование невыгодно"

    return RefinanceResp(
        current=items,
        current_total_remaining=round(total_remaining, 2),
        current_total_payments_left_sum=round(total_payments_left, 2),
        current_total_interest_left=round(total_interest_left, 2),
        new_principal=round(new_principal, 2),
        new_monthly_payment=round(new_monthly, 2),
        new_total_payments_sum=round(new_total, 2),
        new_total_interest=round(new_interest, 2),
        savings_rub=round(savings, 2),
        savings_pct=round(savings_pct, 2),
        recommendation=rec,
        breakeven_months=breakeven,
        note=(
            "Сравнение: остаток платежей по текущим кредитам vs новый аннуитет. "
            "Не учитывает: страховку, единоразовые комиссии, изменение валюты."
        ),
    )


@router.get("/refinance/preview", response_model=list[LoanCmp])
async def refinance_preview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LoanCmp]:
    """Список активных кредитов с остатками — для UI выбора."""
    loans = (await db.execute(
        select(Loan).where(
            Loan.company_id == current_user.company_id,
            Loan.status == "active",
        )
    )).scalars().all()

    items: list[LoanCmp] = []
    for loan in loans:
        pays = (await db.execute(
            select(LoanPayment).where(
                LoanPayment.loan_id == loan.id,
                LoanPayment.is_paid == False,
            )
        )).scalars().all()
        remaining_p = sum(float(p.principal_part or 0) for p in pays)
        remaining_i = sum(float(p.interest_part or 0) for p in pays)
        remaining_f = sum(float(p.fee_part or 0) for p in pays)
        sum_left = remaining_p + remaining_i + remaining_f

        items.append(LoanCmp(
            loan_id=str(loan.id), lender=loan.lender,
            current_remaining_principal=round(remaining_p, 2),
            current_rate_pct=float(loan.rate_pct or 0),
            current_payments_left=len(pays),
            current_remaining_payments_sum=round(sum_left, 2),
            current_remaining_interest=round(remaining_i + remaining_f, 2),
        ))
    return items
