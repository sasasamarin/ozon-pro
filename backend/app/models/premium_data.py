"""Premium Plus endpoints — таблицы данных.

- ProductQueriesDaily: /v1/analytics/product-queries (семантика товара)
- RealizationDaily: /v1/finance/realization/by-day (посуточная реализация)
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProductQueriesDaily(Base):
    __tablename__ = "product_queries_daily"
    __table_args__ = (
        Index("ix_pq_date", "date"),
        Index("ix_pq_product_date", "product_id", "date"),
    )

    cabinet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    sku: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    offer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unique_search_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unique_view_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    view_conversion: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    gmv: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RealizationDaily(Base):
    __tablename__ = "realization_daily"
    __table_args__ = (
        Index("ix_rd_day", "day"),
        Index("ix_rd_product_day", "product_id", "day"),
    )

    cabinet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    sku: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    offer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qty_sold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qty_returned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weighted_cp: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    weighted_sp: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    sum_bonus: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    sum_fee: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    rows_aggregated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
