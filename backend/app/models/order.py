"""
Модели заказов, транзакций, аналитики.

- Order: заказ Озона (FBO/FBS)
- OrderItem: позиции заказа
- Transaction: транзакции (финансы) - TimescaleDB hypertable
- AnalyticsDaily: ежедневные метрики воронки - TimescaleDB hypertable
"""
import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel


class OrderStatus(str, Enum):
    """Статусы заказа Озона."""

    AWAITING_PACKAGING = "awaiting_packaging"
    AWAITING_DELIVER = "awaiting_deliver"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    NOT_ACCEPTED = "not_accepted"
    ARBITRATION = "arbitration"


class OrderType(str, Enum):
    FBO = "fbo"  # склад Озона
    FBS = "fbs"  # свой склад
    RFBS = "rfbs"


class Order(BaseModel):
    """Заказ Озона."""

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint(
            "ozon_account_id", "posting_number", name="uq_orders_account_posting"
        ),
        Index("ix_orders_created", "created_at"),
        Index("ix_orders_status", "status"),
    )

    # Мультитенантность
    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Идентификаторы Озона
    order_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    order_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    posting_number: Mapped[str] = mapped_column(String(100), nullable=False)

    # Тип и статус
    order_type: Mapped[str] = mapped_column(String(10), nullable=False)  # fbo/fbs
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    substatus: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Финансы
    total_amount: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    commission_amount: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    delivery_price: Mapped[float] = mapped_column(Numeric(15, 2), default=0)

    # География
    cluster_from: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cluster_to: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delivery_method_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Тайминги
    order_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    shipment_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    in_process_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivering_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Сырые данные Озона
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)

    # Связи
    ozon_account = relationship("OzonAccount")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(BaseModel):
    """Позиция заказа (один товар в заказе)."""

    __tablename__ = "order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # SKU из Озона (если ещё не привязали к product)
    ozon_sku: Mapped[int] = mapped_column(BigInteger, nullable=False)
    offer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Количество и цены
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    total_price: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    commission: Mapped[float] = mapped_column(Numeric(15, 2), default=0)

    # Связи
    order: Mapped[Order] = relationship(back_populates="items")
    product = relationship("Product")


# ============================================
# TIMESCALEDB HYPERTABLES
# ============================================


class TransactionCategory(str, Enum):
    """Высокоуровневая категория транзакции (рассчитывается из operation_type)."""

    ORDERS = "orders"
    RETURNS = "returns"
    SERVICES = "services"
    COMPENSATION = "compensation"
    OTHER = "other"


class Transaction(Base):
    """
    Финансовая транзакция Озона (TimescaleDB hypertable).

    Комиссии/логистику/эквайринг/рекламу/штрафы/хранение мы НЕ считаем сами —
    разносим из payload Ozon (`services[]`). Каждое отдельное удержание
    распределяется в одну из именованных колонок (delivery_to_customer и т.д.).

    PK = (time, ozon_transaction_id) → идемпотентный upsert.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_account_time", "ozon_account_id", "time"),
        Index("ix_transactions_type", "operation_type"),
        Index("ix_transactions_user", "user_id"),
        Index("ix_transactions_category", "category"),
    )

    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )

    # Уникальный ID транзакции из Озона (operation_id в payload)
    ozon_transaction_id: Mapped[str] = mapped_column(
        String(100), primary_key=True, nullable=False
    )

    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Денормализация для быстрых per-user запросов
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    operation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    operation_type_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Дата операции по календарю Ozon (отличается от time — времени проведения)
    operation_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Высокоуровневая категория для группировки в P&L
    category: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Деньги
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    accruals_for_sale: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    sale_commission: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    posting_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Полный массив сервисных удержаний с тайпами Ozon (для drill-down).
    services: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Разнесённые удержания. НЕ СЧИТАЕМ САМИ — берём из services[] Ozon.
    delivery_to_customer: Mapped[float] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)
    return_logistics: Mapped[float] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)
    last_mile: Mapped[float] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)
    storage: Mapped[float] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)
    placement: Mapped[float] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)
    acquiring: Mapped[float] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)
    advertising: Mapped[float] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)
    utilization: Mapped[float] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)
    fine: Mapped[float] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)
    compensation: Mapped[float] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)

    # Сырые данные
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)


class AnalyticsDaily(Base):
    """
    Ежедневная аналитика товара (TimescaleDB hypertable).

    Все метрики воронки за день: показы, клики, корзины, заказы, выкуп.
    """

    __tablename__ = "analytics_daily"
    __table_args__ = (
        Index("ix_analytics_product_date", "product_id", "date"),
    )

    date: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    # Показы
    hits_view_search: Mapped[int] = mapped_column(Integer, default=0)  # в поиске
    hits_view_pdp: Mapped[int] = mapped_column(Integer, default=0)  # карточки
    hits_tocart_search: Mapped[int] = mapped_column(Integer, default=0)
    hits_tocart_pdp: Mapped[int] = mapped_column(Integer, default=0)

    # Сессии
    session_view_search: Mapped[int] = mapped_column(Integer, default=0)
    session_view_pdp: Mapped[int] = mapped_column(Integer, default=0)

    # Конверсии (Ozon отдаёт как доли, могут быть > 1 в патологических случаях →
    # держим запас: до 9999.9999, fail-safe против overflow при backfill).
    conv_tocart_search: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    conv_tocart_pdp: Mapped[float] = mapped_column(Numeric(10, 4), default=0)

    # Заказы
    ordered_units: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    delivered_units: Mapped[int] = mapped_column(Integer, default=0)
    returns: Mapped[int] = mapped_column(Integer, default=0)
    cancellations: Mapped[int] = mapped_column(Integer, default=0)

    # Реклама
    adv_view_pdp: Mapped[int] = mapped_column(Integer, default=0)
    adv_sum_all: Mapped[float] = mapped_column(Numeric(15, 2), default=0)

    # Позиция в категории
    position_category: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Дополнительные метрики
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
