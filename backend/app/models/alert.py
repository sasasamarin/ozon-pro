"""
Алерты и уведомления.

Сценарий:
1. Юзер настраивает AlertRule (UI: /alerts/settings) → пороги, тихие часы, каналы
2. Фоновая задача проверяет данные → создаёт AlertHistory строку
3. По каналам (Telegram/email/in-app) уходит Notification

ВАЖНО: legacy-таблица `markers` из 0001 (event log с value_before/value_after для
AI-анализа эффекта) пока остаётся. AlertRule — отдельная сущность для конфигурации
триггеров, которые юзер видит в UI «Настройки маркеров».
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class AlertMarkerType(str, Enum):
    STOCKOUT = "stockout"
    OVERSTOCK = "overstock"
    SALES_DROP = "sales_drop"
    SALES_SPIKE = "sales_spike"
    LOW_CONVERSION = "low_conversion"
    COMPETITOR_DUMP = "competitor_dump"
    PRICE_BELOW_COST = "price_below_cost"
    MARGIN_BELOW_MIN = "margin_below_min"
    CASHFLOW_GAP = "cashflow_gap"
    AD_BUDGET_EXCEEDED = "ad_budget_exceeded"
    CREDIT_PAYMENT_DUE = "credit_payment_due"
    TAX_DUE = "tax_due"
    NEGATIVE_REVIEW = "negative_review"
    RATING_DROP = "rating_drop"
    POSITION_DROP = "position_drop"
    FBS_NOT_SHIPPED = "fbs_not_shipped"
    RETURN_RECEIVED = "return_received"
    COMMISSION_CHANGE = "commission_change"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertRule(BaseModel):
    """Сконфигурированное правило алерта (то, что в UI называется «маркер»)."""

    __tablename__ = "alert_rules"
    __table_args__ = (Index("ix_alert_rules_user", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    ozon_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        nullable=True,  # NULL = на все кабинеты юзера
    )

    marker_type: Mapped[str] = mapped_column(String(40), nullable=False)
    threshold_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    # JSON-объект {"days": ["mon","tue",...], "from": "22:00", "to": "08:00"}
    quiet_hours_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # JSON-массив каналов: ["telegram", "email", "in_app"]
    channels_json: Mapped[dict] = mapped_column(JSON, default=list, nullable=False)


class AlertHistory(BaseModel):
    """Журнал срабатываний алертов."""

    __tablename__ = "alerts_history"
    __table_args__ = (
        Index("ix_alerts_history_user_triggered", "user_id", "triggered_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    marker_type: Mapped[str] = mapped_column(String(40), nullable=False)
    ozon_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )

    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(
        String(20), default=AlertSeverity.WARNING.value, nullable=False
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class Notification(BaseModel):
    """In-app уведомление для конкретного юзера."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
