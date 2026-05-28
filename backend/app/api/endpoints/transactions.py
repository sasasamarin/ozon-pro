"""
Финансовые транзакции Ozon — таблица + CSV-экспорт.

GET /api/v1/finance/transactions
  ?page=1&page_size=50
  &cabinet_ids=<uuid>&cabinet_ids=<uuid>
  &date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
  &operation_type=<точное равенство>
  &search=<подстрока в posting_number / operation_type_name / description>

GET /api/v1/finance/transactions/export.csv  — те же параметры, streaming-CSV.

Доступные op_type-категории (для UI dropdown) тоже отдаём отдельным
endpoint'ом GET /api/v1/finance/transactions/types — список уникальных
operation_type из БД с человеческими названиями и счётчиками.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, date as date_cls

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import OzonAccount, Transaction, User

router = APIRouter()


# === Schemas ===


class TransactionRow(BaseModel):
    time: str
    operation_type: str
    operation_type_name: str | None
    cabinet_id: str
    cabinet_name: str
    posting_number: str | None
    amount: float
    accruals_for_sale: float | None
    sale_commission: float | None
    description: str | None

    delivery_to_customer: float
    return_logistics: float
    last_mile: float
    storage: float
    placement: float
    acquiring: float
    advertising: float
    utilization: float


class TransactionsListResponse(BaseModel):
    page: int
    page_size: int
    total: int
    sum_amount: float            # Σ amount по фильтру (по всем страницам, не только текущей)
    items: list[TransactionRow]


class OperationTypeOption(BaseModel):
    operation_type: str
    operation_type_name: str | None
    count: int


# === Helpers ===


def _build_filters(
    *,
    account_ids: list[uuid.UUID],
    date_from: date_cls | None,
    date_to: date_cls | None,
    operation_type: str | None,
    search: str | None,
):
    where = [Transaction.ozon_account_id.in_(account_ids)]
    if date_from:
        where.append(Transaction.time >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        where.append(Transaction.time < datetime.combine(date_to, datetime.max.time()))
    if operation_type:
        where.append(Transaction.operation_type == operation_type)
    if search:
        s = f"%{search.strip()}%"
        where.append(
            or_(
                Transaction.posting_number.ilike(s),
                Transaction.operation_type_name.ilike(s),
                Transaction.description.ilike(s),
            )
        )
    return where


async def _company_account_ids(
    db: AsyncSession, *, company_id: uuid.UUID, cabinet_ids: list[uuid.UUID] | None
) -> tuple[list[uuid.UUID], dict[str, str]]:
    """Возвращает (account_ids, {id: name}) с учётом cabinet_ids-фильтра."""
    q = select(OzonAccount.id, OzonAccount.name).where(
        OzonAccount.company_id == company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if cabinet_ids:
        q = q.where(OzonAccount.id.in_(cabinet_ids))
    rows = (await db.execute(q)).all()
    return [r[0] for r in rows], {str(r[0]): r[1] for r in rows}


# === Endpoints ===


@router.get("/types", response_model=list[OperationTypeOption])
async def list_operation_types(
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OperationTypeOption]:
    """Уникальные operation_type в БД для UI-dropdown'a."""
    account_ids, _ = await _company_account_ids(
        db, company_id=current_user.company_id, cabinet_ids=cabinet_ids
    )
    if not account_ids:
        return []

    rows = (
        await db.execute(
            select(
                Transaction.operation_type,
                Transaction.operation_type_name,
                func.count().label("cnt"),
            )
            .where(Transaction.ozon_account_id.in_(account_ids))
            .group_by(Transaction.operation_type, Transaction.operation_type_name)
            .order_by(desc(func.count()))
        )
    ).all()
    return [
        OperationTypeOption(
            operation_type=r.operation_type,
            operation_type_name=r.operation_type_name,
            count=int(r.cnt),
        )
        for r in rows
    ]


@router.get("/", response_model=TransactionsListResponse)
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    operation_type: str | None = Query(None),
    search: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionsListResponse:
    account_ids, cabinet_names = await _company_account_ids(
        db, company_id=current_user.company_id, cabinet_ids=cabinet_ids
    )
    if not account_ids:
        return TransactionsListResponse(
            page=page, page_size=page_size, total=0, sum_amount=0.0, items=[]
        )

    where = _build_filters(
        account_ids=account_ids,
        date_from=date_from,
        date_to=date_to,
        operation_type=operation_type,
        search=search,
    )

    # Total count + sum amount одним запросом
    agg = (
        await db.execute(
            select(
                func.count().label("total"),
                func.coalesce(func.sum(Transaction.amount), 0).label("sum_amount"),
            ).where(*where)
        )
    ).one()
    total = int(agg.total or 0)
    sum_amount = float(agg.sum_amount or 0)

    offset = (page - 1) * page_size
    rows = (
        await db.execute(
            select(Transaction)
            .where(*where)
            .order_by(desc(Transaction.time))
            .offset(offset)
            .limit(page_size)
        )
    ).scalars().all()

    items = [
        TransactionRow(
            time=t.time.isoformat(),
            operation_type=t.operation_type,
            operation_type_name=t.operation_type_name,
            cabinet_id=str(t.ozon_account_id),
            cabinet_name=cabinet_names.get(str(t.ozon_account_id), ""),
            posting_number=t.posting_number,
            amount=float(t.amount or 0),
            accruals_for_sale=float(t.accruals_for_sale) if t.accruals_for_sale is not None else None,
            sale_commission=float(t.sale_commission) if t.sale_commission is not None else None,
            description=t.description,
            delivery_to_customer=float(t.delivery_to_customer or 0),
            return_logistics=float(t.return_logistics or 0),
            last_mile=float(t.last_mile or 0),
            storage=float(t.storage or 0),
            placement=float(t.placement or 0),
            acquiring=float(t.acquiring or 0),
            advertising=float(t.advertising or 0),
            utilization=float(t.utilization or 0),
        )
        for t in rows
    ]

    return TransactionsListResponse(
        page=page,
        page_size=page_size,
        total=total,
        sum_amount=sum_amount,
        items=items,
    )


@router.get("/export.csv")
async def export_transactions_csv(
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    operation_type: str | None = Query(None),
    search: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Streaming CSV (без пагинации). Удобно для бухгалтерии."""
    account_ids, cabinet_names = await _company_account_ids(
        db, company_id=current_user.company_id, cabinet_ids=cabinet_ids
    )
    if not account_ids:
        return StreamingResponse(iter([""]), media_type="text/csv")

    where = _build_filters(
        account_ids=account_ids,
        date_from=date_from,
        date_to=date_to,
        operation_type=operation_type,
        search=search,
    )

    # Streaming через async-generator — не грузим всё в память
    async def gen():
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=";")
        writer.writerow([
            "Дата", "Тип операции", "Название операции", "Кабинет",
            "Posting", "Сумма", "Начислено", "Комиссия", "Описание",
            "Доставка к клиенту", "Возвратная логистика", "Last mile",
            "Хранение", "Размещение", "Эквайринг", "Реклама", "Утилизация",
        ])
        yield buf.getvalue()
        buf.seek(0); buf.truncate()

        # Stream через server-side курсор: 5к строк в батче
        BATCH = 5000
        page = 0
        while True:
            rows = (
                await db.execute(
                    select(Transaction)
                    .where(*where)
                    .order_by(desc(Transaction.time))
                    .offset(page * BATCH)
                    .limit(BATCH)
                )
            ).scalars().all()
            if not rows:
                break
            for t in rows:
                writer.writerow([
                    t.time.isoformat(),
                    t.operation_type,
                    t.operation_type_name or "",
                    cabinet_names.get(str(t.ozon_account_id), ""),
                    t.posting_number or "",
                    f"{float(t.amount or 0):.2f}".replace(".", ","),
                    f"{float(t.accruals_for_sale or 0):.2f}".replace(".", ",") if t.accruals_for_sale is not None else "",
                    f"{float(t.sale_commission or 0):.2f}".replace(".", ",") if t.sale_commission is not None else "",
                    t.description or "",
                    f"{float(t.delivery_to_customer or 0):.2f}".replace(".", ","),
                    f"{float(t.return_logistics or 0):.2f}".replace(".", ","),
                    f"{float(t.last_mile or 0):.2f}".replace(".", ","),
                    f"{float(t.storage or 0):.2f}".replace(".", ","),
                    f"{float(t.placement or 0):.2f}".replace(".", ","),
                    f"{float(t.acquiring or 0):.2f}".replace(".", ","),
                    f"{float(t.advertising or 0):.2f}".replace(".", ","),
                    f"{float(t.utilization or 0):.2f}".replace(".", ","),
                ])
            yield buf.getvalue()
            buf.seek(0); buf.truncate()
            if len(rows) < BATCH:
                break
            page += 1

    filename = f"flowoi_transactions_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(
        gen(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
