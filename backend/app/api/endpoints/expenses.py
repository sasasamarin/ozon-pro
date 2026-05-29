"""
/finance/expenses — внутренние расходы (зарплаты/аренда/налоги).

GET    /api/v1/finance/expenses        — список + period filter
POST   /api/v1/finance/expenses        — создать
PATCH  /api/v1/finance/expenses/{id}   — обновить
DELETE /api/v1/finance/expenses/{id}   — удалить
GET    /api/v1/finance/expenses/stats  — KPI разрез по категориям
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import ExpenseCategory, ExternalExpense, User

router = APIRouter()
UTC = timezone.utc


class ExpenseRow(BaseModel):
    id: str
    date: str
    category: str
    amount: float
    description: str | None
    recurring: bool


class ExpenseCreate(BaseModel):
    date: date_cls
    category: str
    amount: float = Field(gt=0)
    description: str | None = None
    recurring: bool = False


class ExpensesList(BaseModel):
    rows: list[ExpenseRow]
    total_amount: float


class ExpenseStatsRow(BaseModel):
    category: str
    count: int
    total: float


class ExpenseStats(BaseModel):
    total_amount: float
    rows: list[ExpenseStatsRow]


def _to_row(e: ExternalExpense) -> ExpenseRow:
    return ExpenseRow(
        id=str(e.id),
        date=e.date.isoformat(),
        category=e.category,
        amount=float(e.amount),
        description=e.description,
        recurring=e.recurring,
    )


@router.get("/", response_model=ExpensesList)
async def list_expenses(
    days: int = Query(90, ge=1, le=730),
    category: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExpensesList:
    cutoff = datetime.now(UTC).date() - timedelta(days=days)
    q = select(ExternalExpense).where(
        ExternalExpense.user_id == current_user.id,
        ExternalExpense.date >= cutoff,
    )
    if category:
        q = q.where(ExternalExpense.category == category)
    q = q.order_by(desc(ExternalExpense.date))
    rows = (await db.execute(q)).scalars().all()
    return ExpensesList(
        rows=[_to_row(e) for e in rows],
        total_amount=round(sum(float(e.amount) for e in rows), 2),
    )


@router.post("/", response_model=ExpenseRow)
async def create_expense(
    payload: ExpenseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseRow:
    if payload.category not in [c.value for c in ExpenseCategory]:
        raise HTTPException(400, f"Невалидная категория: {payload.category}")
    e = ExternalExpense(
        user_id=current_user.id,
        date=payload.date,
        category=payload.category,
        amount=payload.amount,
        description=payload.description,
        recurring=payload.recurring,
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return _to_row(e)


@router.delete("/{expense_id}")
async def delete_expense(
    expense_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        eid = uuid.UUID(expense_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")
    e = (await db.execute(
        select(ExternalExpense).where(
            ExternalExpense.id == eid, ExternalExpense.user_id == current_user.id
        )
    )).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "Не найдено")
    await db.delete(e)
    await db.commit()
    return {"deleted": True}


@router.get("/stats", response_model=ExpenseStats)
async def expense_stats(
    days: int = Query(90, ge=1, le=730),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseStats:
    cutoff = datetime.now(UTC).date() - timedelta(days=days)
    rows = (await db.execute(
        select(
            ExternalExpense.category,
            func.count().label("cnt"),
            func.coalesce(func.sum(ExternalExpense.amount), 0).label("total"),
        )
        .where(
            ExternalExpense.user_id == current_user.id,
            ExternalExpense.date >= cutoff,
        )
        .group_by(ExternalExpense.category)
        .order_by(desc("total"))
    )).all()
    total = sum(float(r.total or 0) for r in rows)
    return ExpenseStats(
        total_amount=round(total, 2),
        rows=[
            ExpenseStatsRow(
                category=r.category, count=int(r.cnt), total=float(r.total or 0)
            )
            for r in rows
        ],
    )
