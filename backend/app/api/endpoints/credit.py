"""
/credit — Ozon-кредитование (read-only).

GET /api/v1/credit/list → активные финансовые продукты Ozon
GET /api/v1/credit/movements/{id} → движения по конкретному продукту
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import OzonAccount, User
from app.models.financing import OzonFinancing, OzonFinancingMovement

router = APIRouter()


PRODUCT_LABELS = {
    "advance_before_sale": "Аванс до продажи",
    "early_payout": "Досрочная выплата",
    "loan_purchase": "Кредит на закупку",
    "loan_working_capital": "Оборотный кредит",
    "commission_installment": "Рассрочка комиссии",
    "external_loan": "Внешний кредит",
}


class CreditRow(BaseModel):
    id: str
    product_type: str
    product_type_label: str
    cabinet_name: str
    principal: float
    interest_rate: float | None
    issued_at: str
    due_date: str | None
    status: str
    current_debt: float


class MovementRow(BaseModel):
    time: str
    movement_type: str
    amount: float
    affects_pnl: bool
    affects_cashflow: bool


class CreditSummary(BaseModel):
    total_active_debt: float
    total_pnl_interest: float
    items: list[CreditRow]


@router.get("/list", response_model=CreditSummary)
async def list_credits(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreditSummary:
    accs = (await db.execute(
        select(OzonAccount.id, OzonAccount.name).where(
            OzonAccount.company_id == current_user.company_id,
            OzonAccount.deleted_at.is_(None),
        )
    )).all()
    if not accs:
        return CreditSummary(total_active_debt=0, total_pnl_interest=0, items=[])

    acc_map = {a[0]: a[1] for a in accs}
    rows = (await db.execute(
        select(OzonFinancing).where(
            OzonFinancing.ozon_account_id.in_([a[0] for a in accs])
        ).order_by(desc(OzonFinancing.issued_at))
    )).scalars().all()

    items: list[CreditRow] = []
    total_debt = 0.0
    total_pnl = 0.0
    for fin in rows:
        # current debt = sum movements.affects_debt
        debt_row = await db.execute(
            select(func.coalesce(func.sum(OzonFinancingMovement.affects_debt), 0))
            .where(OzonFinancingMovement.financing_id == fin.id)
        )
        debt = float(debt_row.scalar() or 0)

        pnl_row = await db.execute(
            select(func.coalesce(func.sum(OzonFinancingMovement.amount), 0))
            .where(
                OzonFinancingMovement.financing_id == fin.id,
                OzonFinancingMovement.affects_pnl.is_(True),
            )
        )
        pnl = float(pnl_row.scalar() or 0)
        total_pnl += pnl

        if fin.status in ("active", "repaying"):
            total_debt += debt

        items.append(CreditRow(
            id=str(fin.id),
            product_type=fin.product_type,
            product_type_label=PRODUCT_LABELS.get(fin.product_type, fin.product_type),
            cabinet_name=acc_map.get(fin.ozon_account_id, ""),
            principal=float(fin.principal),
            interest_rate=float(fin.interest_rate) if fin.interest_rate is not None else None,
            issued_at=fin.issued_at.isoformat(),
            due_date=fin.due_date.isoformat() if fin.due_date else None,
            status=fin.status,
            current_debt=round(debt, 2),
        ))

    return CreditSummary(
        total_active_debt=round(total_debt, 2),
        total_pnl_interest=round(total_pnl, 2),
        items=items,
    )


@router.get("/movements/{financing_id}", response_model=list[MovementRow])
async def list_movements(
    financing_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MovementRow]:
    try:
        fid = uuid.UUID(financing_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")

    fin = (await db.execute(
        select(OzonFinancing).join(OzonAccount, OzonAccount.id == OzonFinancing.ozon_account_id)
        .where(
            OzonFinancing.id == fid,
            OzonAccount.company_id == current_user.company_id,
        )
    )).scalar_one_or_none()
    if not fin:
        raise HTTPException(404, "Не найдено")

    rows = (await db.execute(
        select(OzonFinancingMovement)
        .where(OzonFinancingMovement.financing_id == fid)
        .order_by(desc(OzonFinancingMovement.time))
        .limit(500)
    )).scalars().all()

    return [
        MovementRow(
            time=m.time.isoformat(),
            movement_type=m.movement_type,
            amount=float(m.amount),
            affects_pnl=m.affects_pnl,
            affects_cashflow=m.affects_cashflow,
        )
        for m in rows
    ]
