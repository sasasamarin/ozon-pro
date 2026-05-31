"""
AI-контекст endpoint — выдаёт полную картину товара для AI или внешних агрегаторов.

GET /api/v1/ai/context/{product_id} → JSON со всем (продажи, расходы,
маржа после налога, остатки, воронка, реклама).

Сейчас используется в UI (карточка товара показывает экономику).
Когда подключим AI-прокси (Render) — этот endpoint станет источником
данных для function calling.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.services.analytics_engine import get_full_context

router = APIRouter()


@router.get("/context/{product_id}")
async def product_full_context(
    product_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    ctx = await get_full_context(
        db, product_id=product_id, company_id=current_user.company_id, days=days,
    )
    if ctx.get("error"):
        raise HTTPException(404, ctx["error"])
    return ctx


class AskRequest(BaseModel):
    product_id: uuid.UUID | None = None
    question: str
    context_days: int = 30


class AskResponse(BaseModel):
    answer: str
    used_context: dict
    provider: str
    status: str          # 'ready' | 'not_configured' | 'error'


@router.post("/ask", response_model=AskResponse)
async def ai_ask(
    body: AskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AskResponse:
    """
    AI-вопрос. Каркас — пока без Render-прокси.

    Когда юзер подключит Render с AI-сервисом:
    1. Соберём контекст через get_full_context
    2. Отправим в Render → Anthropic/OpenAI
    3. Получим ответ с function_calls к нашим расчётам
    4. Вернём связный текст

    Пока возвращаем заглушку с собранным контекстом, чтобы UI
    можно было верстать и тестировать сборку данных.
    """
    if body.product_id:
        ctx = await get_full_context(
            db, product_id=body.product_id,
            company_id=current_user.company_id,
            days=body.context_days,
        )
    else:
        ctx = {"note": "agg context — not implemented yet"}

    return AskResponse(
        answer=(
            "AI-аналитик пока не подключён. Контекст собран и доступен в used_context. "
            "Чтобы активировать, разверни Render-прокси с Anthropic API и пропиши "
            "AI_PROXY_URL + AI_PROXY_TOKEN в .env. См. project_flowoi_ai_architecture."
        ),
        used_context=ctx,
        provider="none",
        status="not_configured",
    )
