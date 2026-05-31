"""
sync_state — курсор синхронизации по паре (cabinet, endpoint).

Позволяет orchestrator'у возобновляться с последнего успешного дня, а не
гонять весь диапазон с нуля при каждом падении. Главное лекарство от
«2-3 суток вместо 30 минут» когда часть чанков фейлится по 429.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SyncState(Base):
    """Курсор синхронизации (cabinet_id, endpoint)."""

    __tablename__ = "sync_state"

    cabinet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    endpoint: Mapped[str] = mapped_column(String(100), primary_key=True)
    # Окно покрытия [last_synced_from .. last_cursor].
    # last_synced_from — нижняя граница окна (для какого диапазона делали ре-проверку);
    # last_cursor — верхняя граница, ISO даты/datetime в зависимости от эндпоинта.
    last_synced_from: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    # ok / running / error — для UI индикатора и для guard против двойного запуска
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
