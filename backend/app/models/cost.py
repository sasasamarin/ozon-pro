"""
Себестоимость, поставщики, импорт прайса.

- Supplier            — справочник поставщиков
- SupplierOrder       — заказ поставщику, при receive → пишет в ProductCostHistory
- ProductCostHistory  — point-in-time стоимость товара (TimescaleDB hypertable)
- CostImportLog       — лог импорта из CSV / Google Sheets / 1C
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModel


class CostSource(str, Enum):
    MANUAL = "manual"
    CSV = "csv"
    GOOGLE_SHEET = "google_sheet"
    SUPPLIER_ORDER = "supplier_order"
    API_1C = "api_1c"


class CostConfidence(str, Enum):
    EXACT = "exact"
    ESTIMATED = "estimated"
    MISSING = "missing"


class SupplierOrderStatus(str, Enum):
    CREATED = "created"
    PAID = "paid"
    IN_TRANSIT = "in_transit"
    RECEIVED = "received"
    PARTIAL = "partial"


class Supplier(BaseModel):
    __tablename__ = "suppliers"
    __table_args__ = (Index("ix_suppliers_user", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SupplierOrder(BaseModel):
    """Заказ поставщику. При receive → пишет ProductCostHistory с source=supplier_order."""

    __tablename__ = "supplier_orders"
    __table_args__ = (Index("ix_supplier_orders_user_product", "user_id", "product_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    ozon_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ozon_accounts.id", ondelete="SET NULL"), nullable=True
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )

    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    delivery_cost: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20),
        default=SupplierOrderStatus.CREATED.value,
        server_default=SupplierOrderStatus.CREATED.value,
        nullable=False,
    )


# ============================================================
# HYPERTABLE: product_cost_history
# ============================================================


class ProductCostHistory(Base):
    """
    Point-in-time себестоимость с слоями (закупка / доставка / упаковка / прочее).

    Hypertable по `effective_from`. PK = (effective_from, product_id) — на один
    товар в одну точку времени = одна актуальная стоимость.
    """

    __tablename__ = "product_cost_history"
    __table_args__ = (
        Index("ix_product_cost_user", "user_id"),
        # NB: id NOT unique — TimescaleDB не разрешает UNIQUE без partitioning column.
        # Уникальность даёт composite PK (effective_from, product_id).
    )

    # Hypertable PK: (effective_from, product_id)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), default=uuid.uuid4, nullable=False
    )

    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ozon_accounts.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    effective_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Слои себестоимости
    purchase_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    delivery_to_wh: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    packaging: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    other_costs: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    full_cost: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    source: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[str] = mapped_column(
        String(20), default=CostConfidence.EXACT.value, nullable=False
    )

    currency: Mapped[str] = mapped_column(String(3), default="RUB", server_default="RUB", nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class CostImportLog(BaseModel):
    __tablename__ = "cost_import_log"
    __table_args__ = (Index("ix_cost_import_log_user", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
