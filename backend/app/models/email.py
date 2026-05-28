"""
Email-логирование. Сами шаблоны — заглушки в services/email.py.

email_log пишется ДО отправки (status=queued), обновляется sent/failed
после.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class EmailTemplate(str, Enum):
    WELCOME = "welcome"
    VERIFY_EMAIL = "verify_email"
    PASSWORD_RESET = "password_reset"
    LOGIN_ALERT = "login_alert"
    FIRST_SYNC_DONE = "first_sync_done"
    WEEKLY_DIGEST = "weekly_digest"
    MARKER_ALERT = "marker_alert"


class EmailStatus(str, Enum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"


class EmailLog(BaseModel):
    __tablename__ = "email_log"
    __table_args__ = (
        Index("ix_email_log_user_created", "user_id", "created_at"),
        Index("ix_email_log_status", "status"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    template: Mapped[str] = mapped_column(String(40), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=EmailStatus.QUEUED.value, nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
