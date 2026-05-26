"""
Модели для подключения к Озону.

- OzonAccount: один магазин Озона (у пользователя их может быть несколько)
- SyncLog: лог синхронизаций с Озоном (важно для отладки)

ВАЖНО: API ключи Озона ХРАНЯТСЯ ЗАШИФРОВАННЫМИ (через app.core.security.encrypt_secret)
"""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, SoftDeleteMixin


class OzonAccountStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"  # ошибка авторизации
    SYNCING = "syncing"


class OzonAccount(BaseModel, SoftDeleteMixin):
    """
    Магазин Озона.

    У одной Company может быть несколько магазинов (у тебя их 4).
    Каждый магазин имеет свои API ключи (Seller + Performance).
    """

    __tablename__ = "ozon_accounts"

    # Связь с компанией (мультитенантность)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Идентификация магазина
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # API ключи (ЗАШИФРОВАНЫ через Fernet)
    # Seller API
    client_id_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    # Performance API (для рекламы) — опционально
    perf_client_id_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    perf_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Статус
    status: Mapped[str] = mapped_column(
        String(20),
        default=OzonAccountStatus.ACTIVE.value,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Синхронизация
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Метаданные с Озона (заполняется при синхронизации)
    seller_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    # Связи
    company = relationship("Company", back_populates="ozon_accounts")
    sync_logs: Mapped[list["SyncLog"]] = relationship(
        back_populates="ozon_account", cascade="all, delete-orphan"
    )


class SyncStatus(str, Enum):
    """Статус синхронизации."""

    STARTED = "started"
    SUCCESS = "success"
    PARTIAL = "partial"  # частичный успех (что-то загрузилось, что-то нет)
    FAILED = "failed"


class SyncLog(BaseModel):
    """
    Лог каждой синхронизации с Озоном.

    Зачем:
    - Видеть когда Озон API упал
    - Какие данные не загрузились
    - Сколько времени заняла синхронизация
    - Сколько записей обработано
    """

    __tablename__ = "sync_logs"

    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Что синхронизировали
    method: Mapped[str] = mapped_column(String(100), nullable=False)
    # например: "sync_products", "sync_orders", "sync_transactions"

    # Статус
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    # Тайминги
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Статистика
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)

    # Ошибки
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Связи
    ozon_account: Mapped[OzonAccount] = relationship(back_populates="sync_logs")
