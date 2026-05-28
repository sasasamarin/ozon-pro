"""
AI-чат: использование (лимиты по тарифу) + история диалогов.

Сам AI пока НЕ реализован — здесь только структура.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class AIModel(str, Enum):
    GPT_4O_MINI = "gpt_4o_mini"
    GPT_4O = "gpt_4o"
    O1 = "o1"


class AIMessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class AIUsageMonthly(BaseModel):
    """Месячный счётчик использования AI на пару (user, model)."""

    __tablename__ = "ai_usage_monthly"
    __table_args__ = (
        UniqueConstraint("user_id", "period", "model", name="uq_ai_usage_monthly_triple"),
        Index("ix_ai_usage_monthly_user", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Формат "YYYY-MM"
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    model: Mapped[str] = mapped_column(String(30), nullable=False)

    requests_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_input: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    tokens_output: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)


class AIChat(BaseModel):
    __tablename__ = "ai_chats"
    __table_args__ = (Index("ix_ai_chats_user", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AIMessage(BaseModel):
    __tablename__ = "ai_messages"
    __table_args__ = (Index("ix_ai_messages_chat_created", "chat_id", "created_at"),)

    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_chats.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    model_used: Mapped[str | None] = mapped_column(String(30), nullable=True)
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context_page: Mapped[str | None] = mapped_column(String(255), nullable=True)
