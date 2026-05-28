"""
Модели для маркеров и аудита.

- Marker: события и изменения (ручные + авто)
- AuditLog: журнал действий пользователей (security)
"""
import uuid
from enum import Enum

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class MarkerType(str, Enum):
    """Типы маркеров."""

    # Ручные (пользователь добавил)
    MANUAL_NOTE = "manual_note"
    PRICE_CHANGE = "price_change"
    CONTENT_UPDATE = "content_update"
    PHOTO_UPDATE = "photo_update"
    PROMO_START = "promo_start"
    PROMO_END = "promo_end"
    AD_CAMPAIGN_START = "ad_campaign_start"
    PROCUREMENT = "procurement"  # закупка

    # Авто (система обнаружила)
    AUTO_STOCK_LOW = "auto_stock_low"
    AUTO_STOCK_OUT = "auto_stock_out"
    AUTO_PRICE_INDEX_CHANGED = "auto_price_index_changed"
    AUTO_COMPETITOR_PRICE_CHANGED = "auto_competitor_price_changed"
    AUTO_POSITION_DROPPED = "auto_position_dropped"
    AUTO_REVIEW_RECEIVED = "auto_review_received"
    AUTO_ANOMALY_DETECTED = "auto_anomaly_detected"


class Marker(BaseModel):
    """
    Маркер события (timeline).

    Это сердце системы — фиксируем ВСЁ что происходит,
    потом AI учится на этом и говорит "что сработало".
    """

    __tablename__ = "markers"
    __table_args__ = (
        Index("ix_markers_created", "created_at"),
        Index("ix_markers_type", "marker_type"),
    )

    # Мультитенантность
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Кто создал (null если автоматический маркер)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # К чему привязан (опционально — может быть общий маркер для магазина)
    ozon_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Тип и описание
    marker_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Значения "до" и "после" (для AI анализа эффекта)
    value_before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    value_after: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Эффект (заполняется через N дней через AI)
    effect_calculated_at: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    effect_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Например: {"sales_change_pct": 87, "profit_change_pct": 32, "days": 7}

    # Связи
    product = relationship("Product", back_populates="markers")


class AuditLog(BaseModel):
    """
    Журнал действий пользователей (security audit).

    Что записываем:
    - Логины/логауты
    - Изменения настроек (особенно API ключей)
    - Изменения цен, себестоимости
    - Создание/удаление товаров, маркеров
    - Подключение/отключение магазинов
    - Экспорт отчётов

    Хранение: 1 год минимум (потом архивируем в S3).
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_company_created", "company_id", "created_at"),
        Index("ix_audit_logs_action", "action"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Действие
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    # Например: "login", "logout", "product.price.update", "ozon_account.create"

    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Контекст
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Данные изменения
    payload_before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    payload_after: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Доп. метаданные (произвольный JSON-контекст события)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
