"""
Чаты с покупателями.

Reviews и Questions — уже в Phase 1 (models/marketplace.py).
Здесь только Chat / ChatMessage.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


from app.db.base import BaseModel


class ChatMessageSender(str, Enum):
    CUSTOMER = "customer"
    SELLER = "seller"
    SYSTEM = "system"


class Chat(BaseModel):
    __tablename__ = "chats"
    __table_args__ = (
        Index("ix_chats_user", "user_id"),
        Index("ix_chats_ozon_chat", "ozon_chat_id"),
    )

    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ozon_accounts.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    ozon_chat_id: Mapped[str] = mapped_column(String(100), nullable=False)
    posting_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unread_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)


class ChatMessage(BaseModel):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_chat", "chat_id"),)

    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    ozon_message_id: Mapped[str] = mapped_column(String(100), nullable=False)
    sender: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attachments_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
