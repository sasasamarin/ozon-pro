"""
/loans — ручной учёт настоящих займов (Ozon.Invest, банковские кредиты).

Тело займа — только в ДДС, в P&L никогда. Расход в P&L — interest_part + fee_part.

GET    /loans                       — список договоров с агрегатами
POST   /loans                       — создать договор + сгенерировать график
GET    /loans/{id}                  — детали договора
DELETE /loans/{id}                  — удалить договор (cascade payments)
GET    /loans/{id}/payments         — график/факт платежей
POST   /loans/{id}/payments/{seq}/pay  — отметить платёж как фактически внесённый
POST   /loans/{id}/payments         — добавить ручной платёж (вне графика)
GET    /loans/aggregate/period      — Σ interest+fee за период (для P&L) + ДДС-флоу
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Loan, LoanPayment, OzonAccount, User
from app.services.loan_schedule import build_schedule

router = APIRouter()
UTC = timezone.utc


# ============================================================
# Schemas
# ============================================================


class LoanCreate(BaseModel):
    lender: str | None = None
    principal: Decimal = Field(..., gt=0)
    rate_pct: Decimal | None = Field(None, ge=0, le=200)
    issued_at: date_cls
    term_months: int | None = Field(None, ge=1, le=600)
    schedule_type: str = Field("annuity", pattern="^(annuity|differentiated|manual)$")
    cabinet_id: uuid.UUID | None = None
    note: str | None = None


class PaymentRow(BaseModel):
    id: str
    seq: int
    pay_date: str
    principal_part: float
    interest_part: float
    fee_part: float
    is_paid: bool
    paid_at: str | None
    source: str
    note: str | None


class LoanRow(BaseModel):
    id: str
    lender: str | None
    principal: float
    rate_pct: float | None
    issued_at: str
    term_months: int | None
    schedule_type: str
    status: str
    note: str | None
    cabinet_id: str | None
    # агрегаты
    total_principal_paid: float
    total_interest_paid: float
    total_fee_paid: float
    remaining_principal: float
    next_pay_date: str | None


class LoansListResponse(BaseModel):
    items: list[LoanRow]
    total_active_principal: float       # ΣΣ остатки по active
    total_interest_ytd: float           # Σ interest_part (is_paid=true) за календарный год
    total_fee_ytd: float


class ManualPayment(BaseModel):
    pay_date: date_cls
    principal_part: Decimal = Field(0, ge=0)
    interest_part: Decimal = Field(0, ge=0)
    fee_part: Decimal = Field(0, ge=0)
    note: str | None = None


class PeriodAggregate(BaseModel):
    """Для P&L и ДДС."""
    period_from: str
    period_to: str
    # P&L: только interest + fee (по дате фактической оплаты)
    pnl_interest: float
    pnl_fee: float
    pnl_total: float                     # = interest + fee
    # ДДС: получение + полные платежи
    cashflow_inflow_principal: float     # +тело при выдаче (issued_at в окне)
    cashflow_outflow_principal: float    # −тело при погашении (is_paid в окне)
    cashflow_outflow_interest: float
    cashflow_outflow_fee: float


# ============================================================
# Helpers
# ============================================================


async def _get_loan_owned(
    db: AsyncSession, loan_id: uuid.UUID, company_id: uuid.UUID,
) -> Loan:
    loan = (await db.execute(
        select(Loan).where(Loan.id == loan_id, Loan.company_id == company_id)
    )).scalar_one_or_none()
    if not loan:
        raise HTTPException(404, "Договор не найден")
    return loan


async def _summarize(db: AsyncSession, loan: Loan) -> tuple[float, float, float, float, str | None]:
    """Возвращает (paid_principal, paid_interest, paid_fee, remaining, next_pay_date)."""
    rows = (await db.execute(
        select(LoanPayment).where(LoanPayment.loan_id == loan.id)
        .order_by(LoanPayment.seq)
    )).scalars().all()
    paid_p = paid_i = paid_f = Decimal("0")
    next_date: date_cls | None = None
    for p in rows:
        if p.is_paid:
            paid_p += p.principal_part
            paid_i += p.interest_part
            paid_f += p.fee_part
        elif next_date is None:
            next_date = p.pay_date
    remaining = Decimal(loan.principal) - paid_p
    return (
        float(paid_p), float(paid_i), float(paid_f),
        float(remaining),
        next_date.isoformat() if next_date else None,
    )


# ============================================================
# Endpoints
# ============================================================


@router.get("", response_model=LoansListResponse)
async def list_loans(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LoansListResponse:
    loans = (await db.execute(
        select(Loan).where(Loan.company_id == current_user.company_id)
        .order_by(Loan.issued_at.desc())
    )).scalars().all()

    items: list[LoanRow] = []
    total_active_principal = 0.0
    for ln in loans:
        paid_p, paid_i, paid_f, remaining, next_date = await _summarize(db, ln)
        if ln.status == "active":
            total_active_principal += remaining
        items.append(LoanRow(
            id=str(ln.id),
            lender=ln.lender,
            principal=float(ln.principal),
            rate_pct=float(ln.rate_pct) if ln.rate_pct is not None else None,
            issued_at=ln.issued_at.isoformat(),
            term_months=ln.term_months,
            schedule_type=ln.schedule_type,
            status=ln.status,
            note=ln.note,
            cabinet_id=str(ln.cabinet_id) if ln.cabinet_id else None,
            total_principal_paid=round(paid_p, 2),
            total_interest_paid=round(paid_i, 2),
            total_fee_paid=round(paid_f, 2),
            remaining_principal=round(remaining, 2),
            next_pay_date=next_date,
        ))

    # YTD interest + fee по реальным выплатам
    year_start = date_cls(datetime.now(UTC).year, 1, 1)
    ytd_row = (await db.execute(
        select(
            func.coalesce(func.sum(LoanPayment.interest_part), 0),
            func.coalesce(func.sum(LoanPayment.fee_part), 0),
        ).where(
            LoanPayment.company_id == current_user.company_id,
            LoanPayment.is_paid.is_(True),
            LoanPayment.pay_date >= year_start,
        )
    )).one()
    return LoansListResponse(
        items=items,
        total_active_principal=round(total_active_principal, 2),
        total_interest_ytd=float(ytd_row[0] or 0),
        total_fee_ytd=float(ytd_row[1] or 0),
    )


@router.post("", response_model=LoanRow)
async def create_loan(
    payload: LoanCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LoanRow:
    if payload.cabinet_id:
        owns_cabinet = (await db.execute(
            select(OzonAccount.id).where(
                OzonAccount.id == payload.cabinet_id,
                OzonAccount.company_id == current_user.company_id,
            )
        )).scalar_one_or_none()
        if not owns_cabinet:
            raise HTTPException(404, "Кабинет не найден или не принадлежит компании")

    loan = Loan(
        company_id=current_user.company_id,
        user_id=current_user.id,
        cabinet_id=payload.cabinet_id,
        lender=payload.lender,
        principal=payload.principal,
        rate_pct=payload.rate_pct,
        issued_at=payload.issued_at,
        term_months=payload.term_months,
        schedule_type=payload.schedule_type,
        note=payload.note,
    )
    db.add(loan)
    await db.flush()

    # Авто-генерация графика для annuity/differentiated.
    # При schedule_type='manual' — пустой график, юзер вносит платежи руками.
    if payload.schedule_type in ("annuity", "differentiated") and payload.term_months:
        entries = build_schedule(
            principal=payload.principal,
            rate_pct_annual=payload.rate_pct or Decimal("0"),
            term_months=payload.term_months,
            issued_at=payload.issued_at,
            schedule_type=payload.schedule_type,
        )
        for e in entries:
            db.add(LoanPayment(
                loan_id=loan.id,
                company_id=current_user.company_id,
                seq=e.seq,
                pay_date=e.pay_date,
                principal_part=e.principal_part,
                interest_part=e.interest_part,
                fee_part=Decimal("0"),
                is_paid=False,
                source="schedule",
            ))

    await db.commit()
    await db.refresh(loan)
    paid_p, paid_i, paid_f, remaining, next_date = await _summarize(db, loan)
    return LoanRow(
        id=str(loan.id),
        lender=loan.lender,
        principal=float(loan.principal),
        rate_pct=float(loan.rate_pct) if loan.rate_pct is not None else None,
        issued_at=loan.issued_at.isoformat(),
        term_months=loan.term_months,
        schedule_type=loan.schedule_type,
        status=loan.status,
        note=loan.note,
        cabinet_id=str(loan.cabinet_id) if loan.cabinet_id else None,
        total_principal_paid=round(paid_p, 2),
        total_interest_paid=round(paid_i, 2),
        total_fee_paid=round(paid_f, 2),
        remaining_principal=round(remaining, 2),
        next_pay_date=next_date,
    )


@router.delete("/{loan_id}", status_code=204)
async def delete_loan(
    loan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    loan = await _get_loan_owned(db, loan_id, current_user.company_id)
    await db.execute(delete(Loan).where(Loan.id == loan.id))
    await db.commit()


@router.get("/{loan_id}/payments", response_model=list[PaymentRow])
async def list_payments(
    loan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PaymentRow]:
    await _get_loan_owned(db, loan_id, current_user.company_id)
    rows = (await db.execute(
        select(LoanPayment).where(LoanPayment.loan_id == loan_id)
        .order_by(LoanPayment.seq)
    )).scalars().all()
    return [
        PaymentRow(
            id=str(p.id), seq=p.seq, pay_date=p.pay_date.isoformat(),
            principal_part=float(p.principal_part),
            interest_part=float(p.interest_part),
            fee_part=float(p.fee_part),
            is_paid=p.is_paid,
            paid_at=p.paid_at.isoformat() if p.paid_at else None,
            source=p.source, note=p.note,
        ) for p in rows
    ]


@router.post("/{loan_id}/payments/{seq}/pay", response_model=PaymentRow)
async def mark_paid(
    loan_id: uuid.UUID,
    seq: int,
    paid_at: date_cls | None = Query(None,
        description="Если не указано — берём pay_date из графика"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentRow:
    await _get_loan_owned(db, loan_id, current_user.company_id)
    p = (await db.execute(
        select(LoanPayment).where(
            LoanPayment.loan_id == loan_id, LoanPayment.seq == seq
        )
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Платёж не найден")
    p.is_paid = True
    p.paid_at = paid_at or p.pay_date
    await db.commit()
    return PaymentRow(
        id=str(p.id), seq=p.seq, pay_date=p.pay_date.isoformat(),
        principal_part=float(p.principal_part),
        interest_part=float(p.interest_part),
        fee_part=float(p.fee_part),
        is_paid=p.is_paid,
        paid_at=p.paid_at.isoformat() if p.paid_at else None,
        source=p.source, note=p.note,
    )


@router.post("/{loan_id}/payments", response_model=PaymentRow)
async def add_manual_payment(
    loan_id: uuid.UUID,
    payload: ManualPayment,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentRow:
    loan = await _get_loan_owned(db, loan_id, current_user.company_id)
    max_seq = (await db.execute(
        select(func.coalesce(func.max(LoanPayment.seq), 0))
        .where(LoanPayment.loan_id == loan_id)
    )).scalar() or 0
    p = LoanPayment(
        loan_id=loan.id,
        company_id=current_user.company_id,
        seq=int(max_seq) + 1,
        pay_date=payload.pay_date,
        principal_part=payload.principal_part,
        interest_part=payload.interest_part,
        fee_part=payload.fee_part,
        is_paid=True,
        paid_at=payload.pay_date,
        source="manual",
        note=payload.note,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return PaymentRow(
        id=str(p.id), seq=p.seq, pay_date=p.pay_date.isoformat(),
        principal_part=float(p.principal_part),
        interest_part=float(p.interest_part),
        fee_part=float(p.fee_part),
        is_paid=p.is_paid,
        paid_at=p.paid_at.isoformat() if p.paid_at else None,
        source=p.source, note=p.note,
    )


@router.get("/aggregate/period", response_model=PeriodAggregate)
async def aggregate_period(
    days: int = Query(90, ge=1, le=3650),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PeriodAggregate:
    today = datetime.now(UTC).date()
    period_to = date_to or today
    period_from = date_from or (period_to - timedelta(days=days))

    # P&L: interest + fee, фильтр по pay_date (плановая) или paid_at (фактич.) —
    # в МСФО проценты признаются в P&L по методу начисления (pay_date).
    pnl_row = (await db.execute(
        select(
            func.coalesce(func.sum(LoanPayment.interest_part), 0),
            func.coalesce(func.sum(LoanPayment.fee_part), 0),
        ).where(
            LoanPayment.company_id == current_user.company_id,
            LoanPayment.pay_date >= period_from,
            LoanPayment.pay_date <= period_to,
        )
    )).one()
    pnl_interest = float(pnl_row[0] or 0)
    pnl_fee = float(pnl_row[1] or 0)

    # ДДС outflow: только фактически уплаченные платежи (is_paid=true)
    cf_out = (await db.execute(
        select(
            func.coalesce(func.sum(LoanPayment.principal_part), 0),
            func.coalesce(func.sum(LoanPayment.interest_part), 0),
            func.coalesce(func.sum(LoanPayment.fee_part), 0),
        ).where(
            LoanPayment.company_id == current_user.company_id,
            LoanPayment.is_paid.is_(True),
            LoanPayment.paid_at >= period_from,
            LoanPayment.paid_at <= period_to,
        )
    )).one()

    # ДДС inflow: выдачи займов в окне (issued_at)
    cf_in = (await db.execute(
        select(func.coalesce(func.sum(Loan.principal), 0)).where(
            Loan.company_id == current_user.company_id,
            Loan.issued_at >= period_from,
            Loan.issued_at <= period_to,
        )
    )).scalar() or 0

    return PeriodAggregate(
        period_from=period_from.isoformat(),
        period_to=period_to.isoformat(),
        pnl_interest=round(pnl_interest, 2),
        pnl_fee=round(pnl_fee, 2),
        pnl_total=round(pnl_interest + pnl_fee, 2),
        cashflow_inflow_principal=float(cf_in),
        cashflow_outflow_principal=float(cf_out[0] or 0),
        cashflow_outflow_interest=float(cf_out[1] or 0),
        cashflow_outflow_fee=float(cf_out[2] or 0),
    )
