"""
/api/v1/ai/chat (POST) — AI Phase 1 (FLOWOI_AI_TZ §8).
/api/v1/ai/sessions (GET) — список сессий юзера.
/api/v1/ai/sessions/{id} (GET) — сообщения сессии.

Поверх legacy /ai/chats — НОВАЯ пара эндпоинтов для function-calling
с OpenAI, cabinet_scope, attachments (контекст графика, не картинка).
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models import User
from app.models.ai_chat import AIChatSession, AIChatMessage, ChatRole
from app.services.ai import orchestrator
from app.services.ai.llm_provider import get_provider


router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str | None = None
    text: str = Field(min_length=1, max_length=8000)
    cabinet_scope: dict[str, Any] | None = None
    attachments: list[dict[str, Any]] | None = None


class ToolCallLog(BaseModel):
    tool: str
    args: dict
    result_preview: str


class ChatResponse(BaseModel):
    session_id: str
    title: str | None
    answer: str
    model: str
    input_tokens: int
    output_tokens: int
    iterations: int
    tool_calls: list[ToolCallLog]
    error: bool


class SessionItem(BaseModel):
    id: str
    title: str | None
    cabinet_scope: dict | None
    created_at: str
    updated_at: str


class MessageItem(BaseModel):
    id: str
    role: str
    content: str | None
    tool_calls: list[dict] | None
    attachments: list[dict] | None
    model_used: str | None
    created_at: str


class StatusResponse(BaseModel):
    configured: bool
    model: str
    provider: str


@router.get("/v2/status", response_model=StatusResponse)
async def ai_v2_status() -> StatusResponse:
    # AI работает либо через прямой OpenAI (in-process), либо через Render-proxy.
    # VPS в РФ не может в OpenAI → используется Render.
    configured = bool(settings.AI_RENDER_URL) or get_provider().is_configured()
    if settings.AI_RENDER_URL:
        provider_name = "render-proxy"
    else:
        provider_name = get_provider().name
    return StatusResponse(
        configured=configured,
        model=settings.OPENAI_MODEL,
        provider=provider_name,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat_message(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    if not settings.AI_RENDER_URL and not get_provider().is_configured():
        raise HTTPException(503, (
            "AI не настроен. Добавь AI_RENDER_URL (URL Render-сервиса) "
            "ИЛИ OPENAI_API_KEY в env бэкенда."
        ))
    try:
        session = await orchestrator.ensure_session(
            db, current_user.id,
            uuid.UUID(body.session_id) if body.session_id else None,
            cabinet_scope=body.cabinet_scope,
            first_message=body.text,
        )
    except ValueError:
        raise HTTPException(404, "Сессия не найдена")

    result = await orchestrator.chat(
        db, session=session, company_id=current_user.company_id,
        user_text=body.text, attachments=body.attachments,
    )
    return ChatResponse(
        session_id=str(session.id),
        title=session.title,
        answer=result["answer"],
        model=result["model"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        iterations=result["iterations"],
        tool_calls=[
            ToolCallLog(tool=t["tool"], args=t["args"], result_preview=t["result_preview"])
            for t in result["tool_calls"]
        ],
        error=result["error"],
    )


@router.get("/sessions", response_model=list[SessionItem])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionItem]:
    rows = (await db.execute(
        select(AIChatSession)
        .where(AIChatSession.user_id == current_user.id)
        .order_by(AIChatSession.updated_at.desc())
        .limit(100)
    )).scalars().all()
    return [
        SessionItem(
            id=str(s.id), title=s.title, cabinet_scope=s.cabinet_scope,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        )
        for s in rows
    ]


@router.get("/sessions/{session_id}", response_model=list[MessageItem])
async def get_session_messages(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MessageItem]:
    s = (await db.execute(select(AIChatSession).where(
        AIChatSession.id == session_id,
        AIChatSession.user_id == current_user.id,
    ))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Сессия не найдена")

    rows = (await db.execute(
        select(AIChatMessage)
        .where(AIChatMessage.session_id == session_id)
        .order_by(AIChatMessage.created_at)
    )).scalars().all()

    out = []
    for m in rows:
        if m.role == ChatRole.TOOL.value:
            continue
        out.append(MessageItem(
            id=str(m.id), role=m.role, content=m.content,
            tool_calls=m.tool_calls, attachments=m.attachments,
            model_used=m.model_used,
            created_at=m.created_at.isoformat(),
        ))
    return out


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    s = (await db.execute(select(AIChatSession).where(
        AIChatSession.id == session_id,
        AIChatSession.user_id == current_user.id,
    ))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Сессия не найдена")
    await db.delete(s)
    await db.commit()
    return {"deleted": True}
