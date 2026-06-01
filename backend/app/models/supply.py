"""
Поставки (MVP, ручной ввод).

Поставка = «машина/вагон», внутри 1+ SKU. Затраты бывают общие на поставку
(доставка, растаможка) или на конкретный SKU (сертификат). Себестоимость
за единицу юзер считает сам и вписывает в `final_unit_cost`.

Авто-распределения затрат НЕТ.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Supply(Base):
    __tablename__ = "supplies"
    __table_args__ = (
        Index("ix_supplies_company_date", "company_id", "supply_date"),
        Index("ix_supplies_status_expected", "status", "expected_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    cabinet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ozon_accounts.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transport_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    route: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="manual")
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    # Даты MVP
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    dispatch_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    dispatch_from: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actual_departure_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    supply_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ФАЗА 2 (поля заложены, не используются в MVP)
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    shipment_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="arrived")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    items: Mapped[list["SupplyItem"]] = relationship(
        back_populates="supply", cascade="all, delete-orphan", order_by="SupplyItem.created_at"
    )
    costs: Mapped[list["SupplyCost"]] = relationship(
        back_populates="supply", cascade="all, delete-orphan", order_by="SupplyCost.created_at"
    )
    documents: Mapped[list["SupplyDocument"]] = relationship(
        back_populates="supply", cascade="all, delete-orphan", order_by="SupplyDocument.uploaded_at"
    )


class SupplyItem(Base):
    __tablename__ = "supply_items"
    __table_args__ = (
        Index("ix_supply_items_supply", "supply_id"),
        Index("ix_supply_items_product", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    supply_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supplies.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    offer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    final_unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    supply: Mapped[Supply] = relationship(back_populates="items")


class SupplyCost(Base):
    __tablename__ = "supply_costs"
    __table_args__ = (
        Index("ix_supply_costs_supply", "supply_id"),
        CheckConstraint("scope IN ('supply','item')", name="ck_supply_costs_scope"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    supply_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supplies.id", ondelete="CASCADE"), nullable=False
    )
    supply_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supply_items.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    scope: Mapped[str] = mapped_column(String(10), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    supply: Mapped[Supply] = relationship(back_populates="costs")


class SupplyDocument(Base):
    __tablename__ = "supply_documents"
    __table_args__ = (Index("ix_supply_documents_supply", "supply_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    supply_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supplies.id", ondelete="CASCADE"), nullable=False
    )
    supply_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supply_items.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    supply: Mapped[Supply] = relationship(back_populates="documents")
