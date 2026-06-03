"""
AI Phase 1 (FLOWOI_AI_TZ.md §5): ai_chat_sessions + ai_chat_messages.

Отдельная пара таблиц от старого ai_chats/ai_messages — у тех другая
семантика (Anthropic-based старый AI-блок). Новая пара поддерживает
cabinet_scope (контекст активных кабинетов) и attachments
(контекст графика — метрики/период/product_id, НЕ картинка).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM = "system"


class AIChatSession(Base):
    __tablename__ = "ai_chat_sessions"
    __table_args__ = (
        Index("ix_ai_chat_sessions_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # {"cabinet_ids": ["uuid1","uuid2"], "active": "uuid1"} или null = все кабинеты компании
    cabinet_scope: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AIChatMessage(Base):
    __tablename__ = "ai_chat_messages"
    __table_args__ = (
        Index("ix_ai_chat_messages_session_created", "session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{id, name, args, result}] — для assistant tool_calls и tool-response
    tool_calls: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    # [{type:'chart', metrics:[...], period:{from,to}, product_id?}]
    attachments: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)

    model_used: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
