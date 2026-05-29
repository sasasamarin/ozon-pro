"""
/communications — отзывы и вопросы (read-only).

Premium_Pro only у Ozon. UI готов, синк работает если у юзера тариф Pro.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import OzonAccount, Product, User
from app.models.marketplace import Question, Review

router = APIRouter()
UTC = timezone.utc


class ReviewRow(BaseModel):
    id: str
    cabinet_name: str
    product_id: str | None
    product_name: str | None
    offer_id: str | None
    author: str | None
    rating: int | None
    text: str | None
    pluses: str | None
    minuses: str | None
    has_photos: bool
    has_videos: bool
    has_answer: bool
    status: str | None
    created_at_ozon: str | None


class QuestionRow(BaseModel):
    id: str
    cabinet_name: str
    product_id: str | None
    product_name: str | None
    offer_id: str | None
    author: str | None
    text: str
    answer: str | None
    created_at_ozon: str | None
    answer_date: str | None
    status: str | None


async def _accs(db: AsyncSession, company_id: uuid.UUID) -> dict[uuid.UUID, str]:
    rows = (await db.execute(
        select(OzonAccount.id, OzonAccount.name).where(
            OzonAccount.company_id == company_id, OzonAccount.deleted_at.is_(None)
        )
    )).all()
    return {r[0]: r[1] for r in rows}


async def _prods(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, Product]:
    if not ids:
        return {}
    rows = (await db.execute(select(Product).where(Product.id.in_(ids)))).scalars().all()
    return {p.id: p for p in rows}


@router.get("/reviews", response_model=list[ReviewRow])
async def list_reviews(
    days: int = Query(90, ge=1, le=730),
    rating: int | None = Query(None, ge=1, le=5),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ReviewRow]:
    accs = await _accs(db, current_user.company_id)
    if not accs:
        return []
    cutoff = datetime.now(UTC) - timedelta(days=days)
    q = select(Review).where(
        Review.ozon_account_id.in_(list(accs.keys())),
        Review.created_at_ozon >= cutoff,
    )
    if rating:
        q = q.where(Review.rating == rating)
    q = q.order_by(desc(Review.created_at_ozon)).limit(500)
    rows = (await db.execute(q)).scalars().all()
    pids = [r.product_id for r in rows if r.product_id]
    prods = await _prods(db, pids)
    return [
        ReviewRow(
            id=str(r.id),
            cabinet_name=accs.get(r.ozon_account_id, ""),
            product_id=str(r.product_id) if r.product_id else None,
            product_name=prods[r.product_id].name if r.product_id in prods else None,
            offer_id=prods[r.product_id].offer_id if r.product_id in prods else None,
            author=r.author_name,
            rating=r.rating,
            text=r.text,
            pluses=r.pluses,
            minuses=r.minuses,
            has_photos=r.has_photos,
            has_videos=r.has_videos,
            has_answer=r.has_answer,
            status=r.status,
            created_at_ozon=r.created_at_ozon.isoformat() if r.created_at_ozon else None,
        )
        for r in rows
    ]


@router.get("/questions", response_model=list[QuestionRow])
async def list_questions(
    days: int = Query(90, ge=1, le=730),
    only_unanswered: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[QuestionRow]:
    accs = await _accs(db, current_user.company_id)
    if not accs:
        return []
    cutoff = datetime.now(UTC) - timedelta(days=days)
    q = select(Question).where(
        Question.ozon_account_id.in_(list(accs.keys())),
        Question.created_at_ozon >= cutoff,
    )
    if only_unanswered:
        q = q.where(Question.answer_text.is_(None))
    q = q.order_by(desc(Question.created_at_ozon)).limit(500)
    rows = (await db.execute(q)).scalars().all()
    pids = [r.product_id for r in rows if r.product_id]
    prods = await _prods(db, pids)
    return [
        QuestionRow(
            id=str(r.id),
            cabinet_name=accs.get(r.ozon_account_id, ""),
            product_id=str(r.product_id) if r.product_id else None,
            product_name=prods[r.product_id].name if r.product_id in prods else None,
            offer_id=prods[r.product_id].offer_id if r.product_id in prods else None,
            author=r.author_name,
            text=r.text,
            answer=r.answer_text,
            created_at_ozon=r.created_at_ozon.isoformat() if r.created_at_ozon else None,
            answer_date=r.answer_date.isoformat() if r.answer_date else None,
            status=r.status,
        )
        for r in rows
    ]
