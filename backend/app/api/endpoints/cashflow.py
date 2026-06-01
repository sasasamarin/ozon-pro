"""
Cashflow — денежный поток по периодам.

GET /api/v1/finance/cashflow?days=90&granularity=week
  granularity: day | week | month
  cabinet_ids: фильтр

Группируем transactions.amount по периоду:
  inflow (>0)  — приход (продажи, компенсации)
  outflow (<0) — расход (комиссии, услуги, реклама, штрафы)
  net          — sum amount = inflow - |outflow|
  cumulative   — накопительный баланс по периодам

Возвращаем KPI: total_in, total_out, net, end_balance.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import OzonAccount, Transaction, User
from app.models.loan import Loan, LoanPayment

router = APIRouter()
UTC = timezone.utc

_GRANULARITY_MAP = {"day": "day", "week": "week", "month": "month"}


class CashflowPoint(BaseModel):
    period_start: str
    inflow: float
    outflow: float       # положительное число (=|sum negative|)
    net: float           # inflow - outflow
    cumulative: float    # накопительный с начала окна
    # Декомпозиция: займы как отдельная категория (для tooltip/легенды)
    loan_inflow: float = 0    # выдача займов в этом бакете
    loan_outflow: float = 0   # тело+процент+комиссия по фактическим платежам


class CashflowKPI(BaseModel):
    total_inflow: float
    total_outflow: float
    net: float
    end_balance: float
    # Кредиты — отдельные суммы за окно
    loan_inflow_total: float = 0
    loan_outflow_total: float = 0


class CashflowResponse(BaseModel):
    period_from: str
    period_to: str
    granularity: str
    kpi: CashflowKPI
    series: list[CashflowPoint]


async def _account_ids(
    db: AsyncSession, *, company_id: uuid.UUID, cabinet_ids: list[uuid.UUID] | None
) -> list[uuid.UUID]:
    q = select(OzonAccount.id).where(
        OzonAccount.company_id == company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if cabinet_ids:
        q = q.where(OzonAccount.id.in_(cabinet_ids))
    return [r[0] for r in (await db.execute(q)).all()]


@router.get("/", response_model=CashflowResponse)
async def get_cashflow(
    days: int = Query(90, ge=1, le=730),
    granularity: str = Query("week"),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CashflowResponse:
    if granularity not in _GRANULARITY_MAP:
        granularity = "week"
    trunc_unit = _GRANULARITY_MAP[granularity]

    now = datetime.now(UTC)
    period_to = now
    period_from = now - timedelta(days=days)

    accs = await _account_ids(db, company_id=current_user.company_id, cabinet_ids=cabinet_ids)
    if not accs:
        return CashflowResponse(
            period_from=period_from.date().isoformat(),
            period_to=period_to.date().isoformat(),
            granularity=granularity,
            kpi=CashflowKPI(total_inflow=0, total_outflow=0, net=0, end_balance=0),
            series=[],
        )

    bucket = func.date_trunc(trunc_unit, Transaction.time).label("bucket")
    # inflow = sum of positive amounts; outflow = sum of |negative amounts|
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
            Transaction.time >= period_from,
            Transaction.time < period_to,
        )
        .group_by(bucket)
        .order_by(bucket)
    )).all()

    # Аккумулятор по бакетам.
    # tx_* — продажи/услуги Ozon (Transaction.amount).
    # loan_* — займы отдельной серией для UI.
    buckets: dict[str, dict[str, float]] = {}
    def slot(period_start: str) -> dict[str, float]:
        return buckets.setdefault(period_start, {
            "tx_in": 0.0, "tx_out": 0.0,
            "loan_in": 0.0, "loan_out": 0.0,
        })

    for r in rows:
        s = slot(r.bucket.date().isoformat())
        s["tx_in"] += float(r.inflow or 0)
        s["tx_out"] += float(r.outflow or 0)

    # === Кредиты/займы — Ветка 1 ТЗ flowoi_tz_loans.md ===
    loan_bucket = func.date_trunc(trunc_unit, Loan.issued_at).label("bucket")
    loan_in_rows = (await db.execute(
        select(loan_bucket, func.coalesce(func.sum(Loan.principal), 0))
        .where(
            Loan.company_id == current_user.company_id,
            Loan.issued_at >= period_from.date(),
            Loan.issued_at < period_to.date(),
        )
        .group_by(loan_bucket)
    )).all()
    for b, amount in loan_in_rows:
        slot(b.date().isoformat())["loan_in"] += float(amount or 0)

    pay_bucket = func.date_trunc(trunc_unit, LoanPayment.paid_at).label("bucket")
    loan_out_rows = (await db.execute(
        select(
            pay_bucket,
            func.coalesce(func.sum(
                LoanPayment.principal_part + LoanPayment.interest_part + LoanPayment.fee_part
            ), 0),
        )
        .where(
            LoanPayment.company_id == current_user.company_id,
            LoanPayment.is_paid.is_(True),
            LoanPayment.paid_at >= period_from.date(),
            LoanPayment.paid_at < period_to.date(),
        )
        .group_by(pay_bucket)
    )).all()
    for b, amount in loan_out_rows:
        slot(b.date().isoformat())["loan_out"] += float(amount or 0)

    # Сортируем бакеты по дате и собираем series с cumulative.
    series: list[CashflowPoint] = []
    cum = 0.0
    total_in = 0.0
    total_out = 0.0
    loan_in_total = 0.0
    loan_out_total = 0.0
    for period_start in sorted(buckets.keys()):
        s = buckets[period_start]
        inflow = s["tx_in"] + s["loan_in"]
        outflow = s["tx_out"] + s["loan_out"]
        net = inflow - outflow
        cum += net
        total_in += inflow
        total_out += outflow
        loan_in_total += s["loan_in"]
        loan_out_total += s["loan_out"]
        series.append(CashflowPoint(
            period_start=period_start,
            inflow=round(inflow, 2),
            outflow=round(outflow, 2),
            net=round(net, 2),
            cumulative=round(cum, 2),
            loan_inflow=round(s["loan_in"], 2),
            loan_outflow=round(s["loan_out"], 2),
        ))

    return CashflowResponse(
        period_from=period_from.date().isoformat(),
        period_to=period_to.date().isoformat(),
        granularity=granularity,
        kpi=CashflowKPI(
            total_inflow=round(total_in, 2),
            total_outflow=round(total_out, 2),
            net=round(total_in - total_out, 2),
            end_balance=round(cum, 2),
            loan_inflow_total=round(loan_in_total, 2),
            loan_outflow_total=round(loan_out_total, 2),
        ),
        series=series,
    )
