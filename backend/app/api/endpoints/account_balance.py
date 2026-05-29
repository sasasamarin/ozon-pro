"""
/finance/account-balance — текущий баланс счёта Ozon, кумулятивно из transactions.

GET /api/v1/finance/account-balance?days=180&cabinet_ids=...
  → текущий баланс + история по дням
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

router = APIRouter()
UTC = timezone.utc


class BalancePoint(BaseModel):
    date: str
    inflow: float
    outflow: float
    net: float
    cumulative: float


class BalanceResp(BaseModel):
    period_from: str
    period_to: str
    starting_balance: float
    current_balance: float
    total_inflow: float
    total_outflow: float
    series: list[BalancePoint]


@router.get("/", response_model=BalanceResp)
async def get_balance(
    days: int = Query(180, ge=1, le=730),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BalanceResp:
    now = datetime.now(UTC)
    period_to = now
    period_from = now - timedelta(days=days)

    accs_q = select(OzonAccount.id).where(
        OzonAccount.company_id == current_user.company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if cabinet_ids:
        accs_q = accs_q.where(OzonAccount.id.in_(cabinet_ids))
    accs = [r[0] for r in (await db.execute(accs_q)).all()]
    if not accs:
        return BalanceResp(
            period_from=period_from.date().isoformat(),
            period_to=period_to.date().isoformat(),
            starting_balance=0, current_balance=0,
            total_inflow=0, total_outflow=0, series=[],
        )

    # Starting balance = sum amount до period_from
    pre_row = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(
            Transaction.ozon_account_id.in_(accs),
            Transaction.time < period_from,
        )
    )
    starting = float(pre_row.scalar() or 0)

    # Daily aggregation в окне
    rows = (await db.execute(
        select(
            func.date_trunc("day", Transaction.time).label("d"),
            func.coalesce(
                func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)),
                0,
            ).label("inflow"),
            func.coalesce(
                func.sum(case((Transaction.amount < 0, -Transaction.amount), else_=0)),
                0,
            ).label("outflow"),
        )
        .where(
            Transaction.ozon_account_id.in_(accs),
            Transaction.time >= period_from,
            Transaction.time < period_to,
        )
        .group_by("d")
        .order_by("d")
    )).all()

    series: list[BalancePoint] = []
    cum = starting
    total_in, total_out = 0.0, 0.0
    for r in rows:
        inflow = float(r.inflow or 0)
        outflow = float(r.outflow or 0)
        net = inflow - outflow
        cum += net
        total_in += inflow
        total_out += outflow
        series.append(BalancePoint(
            date=r.d.date().isoformat(),
            inflow=round(inflow, 2),
            outflow=round(outflow, 2),
            net=round(net, 2),
            cumulative=round(cum, 2),
        ))

    return BalanceResp(
        period_from=period_from.date().isoformat(),
        period_to=period_to.date().isoformat(),
        starting_balance=round(starting, 2),
        current_balance=round(cum, 2),
        total_inflow=round(total_in, 2),
        total_outflow=round(total_out, 2),
        series=series,
    )
