"""
Планирование закупок: параметры поставки + кэш скорости продаж (два горизонта).

- ProductSupplyParams  — параметры поставщика для каждого товара
                         (lead time, MOQ, batch step, safety stock, стратегия)
- SalesVelocityCache   — пересчитанные показатели скорости продаж
                         (TimescaleDB hypertable, два горизонта + сигнал тренда)

Логика расчёта живёт в app/services/forecasting/ (velocity.py + procurement.py),
здесь только хранение результатов.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModel


class ForecastStrategy(str, Enum):
    CONSERVATIVE = "conservative"
    REACTIVE = "reactive"
    BALANCED = "balanced"


class TrendSignal(str, Enum):
    RISING = "rising"
    STABLE = "stable"
    FALLING = "falling"
    VOLATILE = "volatile"


class ForecastConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ProductSupplyParams(BaseModel):
    __tablename__ = "product_supply_params"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "product_id", "supplier_id",
            name="uq_supply_params_user_product_supplier",
        ),
        Index("ix_supply_params_user_product", "user_id", "product_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )

    # Логистический цикл
    lead_time_total_days: Mapped[int] = mapped_column(Integer, nullable=False)
    lead_time_production_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lead_time_delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lead_time_processing_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Параметры партии
    moq: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    batch_step: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    batch_strict: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    safety_stock_days: Mapped[int] = mapped_column(
        Integer, default=7, server_default="7", nullable=False
    )
    is_primary_supplier: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    # Горизонты прогноза
    longterm_window_days: Mapped[int] = mapped_column(
        Integer, default=365, server_default="365", nullable=False
    )
    shortterm_window_days: Mapped[int] = mapped_column(
        Integer, default=14, server_default="14", nullable=False
    )
    forecast_strategy: Mapped[str] = mapped_column(
        String(20),
        default=ForecastStrategy.BALANCED.value,
        server_default=ForecastStrategy.BALANCED.value,
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


# ============================================================
# HYPERTABLE: sales_velocity_cache
# ============================================================


class SalesVelocityCache(Base):
    """
    Пересчёт скорости продаж в двух горизонтах.

    Hypertable по `time`. PK = (time, product_id) — на товар в момент времени
    одна запись.
    """

    __tablename__ = "sales_velocity_cache"
    __table_args__ = (
        Index("ix_sales_velocity_user_product", "user_id", "product_id"),
        Index("ix_sales_velocity_signal", "trend_signal"),
    )

    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ozon_accounts.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Горизонт 1 (годовая база)
    longterm_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    longterm_avg_daily: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    longterm_seasonal_factor: Mapped[float] = mapped_column(
        Numeric(8, 4), default=1.0, server_default="1.0", nullable=False
    )
    longterm_adjusted_daily: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    longterm_confidence: Mapped[str] = mapped_column(String(20), nullable=False)

    # Горизонт 2 (текущая динамика)
    shortterm_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    shortterm_avg_daily: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)

    # Сопоставление
    trend_ratio: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    trend_signal: Mapped[str] = mapped_column(String(20), nullable=False)

    recommended_daily: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    recommendation_basis: Mapped[str | None] = mapped_column(Text, nullable=True)

    # База расчёта — для прозрачности UI («почему такая рекомендация»)
    total_units_sold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    days_in_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    days_out_of_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
