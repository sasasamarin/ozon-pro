"""
Возвраты + отмены.

GET /api/v1/returns                  — unified таблица returns + cancellations
  ?type=all|returns|cancellations
  ?page=1&page_size=50
  &cabinet_ids=...&date_from=...&date_to=...&search=...
GET /api/v1/returns/stats            — агрегаты: причины, по периодам, top SKU
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls, datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import case, desc, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import OzonAccount, Product, User
from app.models.marketplace import Cancellation, Return

router = APIRouter()
UTC = timezone.utc


class ReturnRow(BaseModel):
    id: str
    kind: str                   # 'return' | 'cancellation'
    cabinet_id: str
    cabinet_name: str
    posting_number: str | None
    product_id: str | None
    product_name: str | None
    offer_id: str | None
    ozon_sku: int | None
    quantity: int
    amount: float | None
    reason: str | None
    status: str | None
    occurred_at: str | None


class ReturnsListResponse(BaseModel):
    page: int
    page_size: int
    total: int
    total_amount: float
    items: list[ReturnRow]


class ReasonAggRow(BaseModel):
    reason: str
    count: int
    total_amount: float


class ReturnsStatsResponse(BaseModel):
    returns_count: int
    cancellations_count: int
    returns_amount: float
    top_reasons_returns: list[ReasonAggRow]
    top_reasons_cancellations: list[ReasonAggRow]


async def _account_ids(
    db: AsyncSession, *, company_id: uuid.UUID, cabinet_ids: list[uuid.UUID] | None
) -> tuple[list[uuid.UUID], dict[str, str]]:
    q = select(OzonAccount.id, OzonAccount.name).where(
        OzonAccount.company_id == company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if cabinet_ids:
        q = q.where(OzonAccount.id.in_(cabinet_ids))
    rows = (await db.execute(q)).all()
    return [r[0] for r in rows], {str(r[0]): r[1] for r in rows}


@router.get("/", response_model=ReturnsListResponse)
async def list_returns(
    kind: str = Query("all", description="all | returns | cancellations"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    search: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReturnsListResponse:
    accs, cabinet_names = await _account_ids(
        db, company_id=current_user.company_id, cabinet_ids=cabinet_ids
    )
    if not accs:
        return ReturnsListResponse(page=page, page_size=page_size, total=0, total_amount=0, items=[])

    items: list[ReturnRow] = []
    total = 0
    total_amount = 0.0

    # === returns ===
    if kind in ("all", "returns"):
        ret_where = [Return.ozon_account_id.in_(accs)]
        if date_from:
            ret_where.append(Return.return_date >= datetime.combine(date_from, datetime.min.time()))
        if date_to:
            ret_where.append(Return.return_date < datetime.combine(date_to, datetime.max.time()))
        if search:
            s = f"%{search.strip()}%"
            ret_where.append(or_(
                Return.posting_number.ilike(s),
                Return.return_reason.ilike(s),
            ))

        ret_count_q = await db.execute(
            select(func.count()).select_from(Return).where(*ret_where)
        )
        ret_count = int(ret_count_q.scalar() or 0)
        ret_sum_q = await db.execute(
            select(func.coalesce(func.sum(Return.return_amount), 0)).where(*ret_where)
        )
        ret_sum = float(ret_sum_q.scalar() or 0)

        total += ret_count
        total_amount += ret_sum

    # === cancellations ===
    if kind in ("all", "cancellations"):
        c_where = [Cancellation.ozon_account_id.in_(accs)]
        if date_from:
            c_where.append(Cancellation.cancelled_at >= datetime.combine(date_from, datetime.min.time()))
        if date_to:
            c_where.append(Cancellation.cancelled_at < datetime.combine(date_to, datetime.max.time()))
        if search:
            s = f"%{search.strip()}%"
            c_where.append(or_(
                Cancellation.posting_number.ilike(s),
                Cancellation.cancel_reason_text.ilike(s),
            ))

        c_count_q = await db.execute(
            select(func.count()).select_from(Cancellation).where(*c_where)
        )
        c_count = int(c_count_q.scalar() or 0)
        total += c_count

    # === fetch items для текущей страницы ===
    # Простой подход: достаём по типу отдельно, потом склеиваем и сортируем.
    # Для смешанного 'all' offset/limit будет приблизительным (отдаём top по дате)
    offset = (page - 1) * page_size

    if kind == "returns":
        rows = (await db.execute(
            select(Return)
            .where(*ret_where)
            .order_by(desc(Return.return_date))
            .offset(offset).limit(page_size)
        )).scalars().all()
        # подгрузим имена товаров одним запросом
        pids = [r.product_id for r in rows if r.product_id]
        prods = await _products_by_ids(db, pids)
        for r in rows:
            p = prods.get(r.product_id) if r.product_id else None
            items.append(ReturnRow(
                id=str(r.id), kind="return",
                cabinet_id=str(r.ozon_account_id),
                cabinet_name=cabinet_names.get(str(r.ozon_account_id), ""),
                posting_number=r.posting_number,
                product_id=str(r.product_id) if r.product_id else None,
                product_name=p.name if p else None,
                offer_id=p.offer_id if p else None,
                ozon_sku=r.ozon_sku,
                quantity=r.quantity or 1,
                amount=float(r.return_amount) if r.return_amount is not None else None,
                reason=r.return_reason,
                status=r.status,
                occurred_at=r.return_date.isoformat() if r.return_date else None,
            ))
    elif kind == "cancellations":
        rows = (await db.execute(
            select(Cancellation)
            .where(*c_where)
            .order_by(desc(Cancellation.cancelled_at))
            .offset(offset).limit(page_size)
        )).scalars().all()
        # cancellations не имеют product_id, ищем по (account, ozon_sku) через products
        skus = [(r.ozon_account_id, r.ozon_sku) for r in rows if r.ozon_sku]
        prods = await _products_by_account_sku(db, skus)
        for r in rows:
            p = prods.get((r.ozon_account_id, r.ozon_sku))
            items.append(ReturnRow(
                id=str(r.id), kind="cancellation",
                cabinet_id=str(r.ozon_account_id),
                cabinet_name=cabinet_names.get(str(r.ozon_account_id), ""),
                posting_number=r.posting_number,
                product_id=str(p.id) if p else None,
                product_name=p.name if p else None,
                offer_id=p.offer_id if p else None,
                ozon_sku=r.ozon_sku,
                quantity=r.quantity or 1,
                amount=None,
                reason=r.cancel_reason_text or (f"reason_id={r.cancel_reason_id}" if r.cancel_reason_id else None),
                status=r.initiator,
                occurred_at=r.cancelled_at.isoformat() if r.cancelled_at else None,
            ))
    else:  # all — union, sort by date desc, limit page
        # Для простоты делаем 2 запроса по page_size и сортируем в Python
        ret_rows = (await db.execute(
            select(Return).where(*ret_where).order_by(desc(Return.return_date))
            .limit(offset + page_size)
        )).scalars().all() if 'ret_where' in dir() else []
        can_rows = (await db.execute(
            select(Cancellation).where(*c_where).order_by(desc(Cancellation.cancelled_at))
            .limit(offset + page_size)
        )).scalars().all() if 'c_where' in dir() else []

        ret_pids = [r.product_id for r in ret_rows if r.product_id]
        ret_prods = await _products_by_ids(db, ret_pids)
        can_skus = [(r.ozon_account_id, r.ozon_sku) for r in can_rows if r.ozon_sku]
        can_prods = await _products_by_account_sku(db, can_skus)

        unified: list[tuple[datetime, ReturnRow]] = []
        for r in ret_rows:
            p = ret_prods.get(r.product_id) if r.product_id else None
            ts = r.return_date or datetime.fromtimestamp(0, UTC)
            unified.append((ts, ReturnRow(
                id=str(r.id), kind="return",
                cabinet_id=str(r.ozon_account_id),
                cabinet_name=cabinet_names.get(str(r.ozon_account_id), ""),
                posting_number=r.posting_number,
                product_id=str(r.product_id) if r.product_id else None,
                product_name=p.name if p else None,
                offer_id=p.offer_id if p else None,
                ozon_sku=r.ozon_sku,
                quantity=r.quantity or 1,
                amount=float(r.return_amount) if r.return_amount is not None else None,
                reason=r.return_reason,
                status=r.status,
                occurred_at=r.return_date.isoformat() if r.return_date else None,
            )))
        for r in can_rows:
            p = can_prods.get((r.ozon_account_id, r.ozon_sku))
            ts = r.cancelled_at or datetime.fromtimestamp(0, UTC)
            unified.append((ts, ReturnRow(
                id=str(r.id), kind="cancellation",
                cabinet_id=str(r.ozon_account_id),
                cabinet_name=cabinet_names.get(str(r.ozon_account_id), ""),
                posting_number=r.posting_number,
                product_id=str(p.id) if p else None,
                product_name=p.name if p else None,
                offer_id=p.offer_id if p else None,
                ozon_sku=r.ozon_sku,
                quantity=r.quantity or 1,
                amount=None,
                reason=r.cancel_reason_text or (f"reason_id={r.cancel_reason_id}" if r.cancel_reason_id else None),
                status=r.initiator,
                occurred_at=r.cancelled_at.isoformat() if r.cancelled_at else None,
            )))
        unified.sort(key=lambda x: x[0], reverse=True)
        items = [row for _, row in unified[offset:offset + page_size]]

    return ReturnsListResponse(
        page=page, page_size=page_size,
        total=total, total_amount=round(total_amount, 2), items=items,
    )


async def _products_by_ids(db: AsyncSession, pids: list[uuid.UUID]) -> dict[uuid.UUID, Product]:
    if not pids:
        return {}
    rows = (await db.execute(select(Product).where(Product.id.in_(pids)))).scalars().all()
    return {p.id: p for p in rows}


async def _products_by_account_sku(
    db: AsyncSession, pairs: list[tuple[uuid.UUID, int]]
) -> dict[tuple[uuid.UUID, int], Product]:
    if not pairs:
        return {}
    # Берём всё подходящее, не идеально, но просто
    skus = list({s for _, s in pairs})
    accs = list({a for a, _ in pairs})
    rows = (await db.execute(
        select(Product).where(
            Product.ozon_sku.in_(skus),
            Product.ozon_account_id.in_(accs),
        )
    )).scalars().all()
    return {(p.ozon_account_id, p.ozon_sku): p for p in rows}


@router.get("/stats", response_model=ReturnsStatsResponse)
async def returns_stats(
    days: int = Query(90, ge=1, le=730),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReturnsStatsResponse:
    from datetime import timedelta
    period_from = datetime.now(UTC) - timedelta(days=days)

    accs, _ = await _account_ids(
        db, company_id=current_user.company_id, cabinet_ids=cabinet_ids
    )
    if not accs:
        return ReturnsStatsResponse(
            returns_count=0, cancellations_count=0, returns_amount=0,
            top_reasons_returns=[], top_reasons_cancellations=[],
        )

    # Returns
    ret_total = (await db.execute(
        select(func.count(), func.coalesce(func.sum(Return.return_amount), 0))
        .where(Return.ozon_account_id.in_(accs), Return.return_date >= period_from)
    )).one()
    ret_reasons = (await db.execute(
        select(
            func.coalesce(Return.return_reason, "(не указано)").label("reason"),
            func.count().label("cnt"),
            func.coalesce(func.sum(Return.return_amount), 0).label("amount"),
        )
        .where(Return.ozon_account_id.in_(accs), Return.return_date >= period_from)
        .group_by("reason")
        .order_by(desc("cnt"))
        .limit(10)
    )).all()

    # Cancellations
    can_total = (await db.execute(
        select(func.count())
        .where(Cancellation.ozon_account_id.in_(accs), Cancellation.cancelled_at >= period_from)
    )).scalar()
    can_reasons = (await db.execute(
        select(
            func.coalesce(Cancellation.cancel_reason_text, "(не указано)").label("reason"),
            func.count().label("cnt"),
        )
        .where(Cancellation.ozon_account_id.in_(accs), Cancellation.cancelled_at >= period_from)
        .group_by("reason")
        .order_by(desc("cnt"))
        .limit(10)
    )).all()

    return ReturnsStatsResponse(
        returns_count=int(ret_total[0] or 0),
        cancellations_count=int(can_total or 0),
        returns_amount=float(ret_total[1] or 0),
        top_reasons_returns=[
            ReasonAggRow(reason=str(r.reason), count=int(r.cnt), total_amount=float(r.amount or 0))
            for r in ret_reasons
        ],
        top_reasons_cancellations=[
            ReasonAggRow(reason=str(r.reason), count=int(r.cnt), total_amount=0)
            for r in can_reasons
        ],
    )
