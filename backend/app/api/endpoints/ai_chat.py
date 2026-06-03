"""
/api/v1/ai/chats/* — реальный AI-чат с tool-calling.
Требует AI_PROXY_URL (Render proxy) либо ANTHROPIC_API_KEY в .env.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models import User
from app.models.ai import AIChat, AIMessage, AIMessageRole
from app.services.ai import chat_service, proxy


router = APIRouter()


# === Schemas ================================================================


class ChatItem(BaseModel):
    id: str
    title: str | None
    created_at: str
    updated_at: str
    last_message_at: str | None


class MessageItem(BaseModel):
    id: str
    role: str
    content: str
    model_used: str | None
    created_at: str


class SendMessageRequest(BaseModel):
    chat_id: str | None = None         # если None — создаём новый чат
    text: str
    model: str | None = None           # переопределить модель
    context_page: str | None = None    # на какой странице был задан вопрос


class SendMessageResponse(BaseModel):
    chat_id: str
    title: str | None
    answer: str
    model: str
    input_tokens: int
    output_tokens: int
    iterations: int
    tool_calls: list[dict]
    error: bool


class StatusResponse(BaseModel):
    configured: bool
    via_proxy: bool
    default_model: str


# === Endpoints ==============================================================


@router.get("/status", response_model=StatusResponse)
async def ai_status() -> StatusResponse:
    """Проверить настройку AI (для UI badge «доступно/не настроено»)."""
    return StatusResponse(
        configured=proxy.is_configured(),
        via_proxy=bool(settings.AI_PROXY_URL),
        default_model=settings.AI_DEFAULT_MODEL,
    )


@router.get("/chats", response_model=list[ChatItem])
async def list_chats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChatItem]:
    rows = (await db.execute(
        select(AIChat).where(AIChat.user_id == current_user.id)
        .order_by(AIChat.updated_at.desc())
        .limit(100)
    )).scalars().all()
    return [
        ChatItem(
            id=str(c.id), title=c.title,
            created_at=c.created_at.isoformat(),
            updated_at=c.updated_at.isoformat() if c.updated_at else c.created_at.isoformat(),
            last_message_at=None,
        )
        for c in rows
    ]


@router.delete("/chats/{chat_id}")
async def delete_chat(
    chat_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    chat = (await db.execute(
        select(AIChat).where(AIChat.id == chat_id, AIChat.user_id == current_user.id)
    )).scalar_one_or_none()
    if not chat:
        raise HTTPException(404, "Чат не найден")
    await db.delete(chat)
    await db.commit()
    return {"deleted": True}


@router.get("/chats/{chat_id}/messages", response_model=list[MessageItem])
async def list_messages(
    chat_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MessageItem]:
    chat = (await db.execute(
        select(AIChat).where(AIChat.id == chat_id, AIChat.user_id == current_user.id)
    )).scalar_one_or_none()
    if not chat:
        raise HTTPException(404, "Чат не найден")
    rows = (await db.execute(
        select(AIMessage).where(AIMessage.chat_id == chat_id)
        .order_by(AIMessage.created_at)
    )).scalars().all()
    out = []
    for m in rows:
        # tool-сообщения скрываем от UI — они служебные
        if m.role == AIMessageRole.TOOL.value:
            continue
        # assistant tool_use-блок (JSON) тоже скрываем — UI рендерит только текст
        content = m.content
        if m.role == AIMessageRole.ASSISTANT.value and content.startswith("["):
            try:
                blocks = json.loads(content)
                if isinstance(blocks, list):
                    text_parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
                    if not text_parts:
                        continue  # только tool_use — пропускаем
                    content = "\n".join(text_parts)
            except (ValueError, TypeError):
                pass
        out.append(MessageItem(
            id=str(m.id), role=m.role, content=content,
            model_used=m.model_used,
            created_at=m.created_at.isoformat(),
        ))
    return out


@router.post("/chats/messages", response_model=SendMessageResponse)
async def send_message(
    body: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SendMessageResponse:
    """
    Отправить сообщение в чат. Если chat_id=null — создаётся новый чат
    с title из первого сообщения.

    Возвращает текст ответа ассистента + статистику tool-вызовов.
    """
    if not body.text.strip():
        raise HTTPException(400, "Пустое сообщение")
    if not proxy.is_configured():
        raise HTTPException(503, (
            "AI не настроен. Добавь AI_PROXY_URL+AI_PROXY_TOKEN или "
            "ANTHROPIC_API_KEY в .env бэкенда."
        ))

    try:
        chat = await chat_service.ensure_chat(
            db, current_user.id,
            uuid.UUID(body.chat_id) if body.chat_id else None,
            first_message=body.text,
        )
    except ValueError:
        raise HTTPException(404, "Чат не найден")

    result = await chat_service.send_message(
        db, chat=chat,
        user_id=current_user.id, company_id=current_user.company_id,
        text=body.text, model=body.model,
        context_page=body.context_page,
    )
    return SendMessageResponse(
        chat_id=str(chat.id),
        title=chat.title,
        answer=result["answer"],
        model=result["model"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        iterations=result["iterations"],
        tool_calls=result["tool_calls"],
        error=result["error"],
    )
