"""
Оценка customer_price для старых месяцев (>90 дней).

Источник — /v2/finance/realization → delivery_commission.price_per_instance,
взвешенное по qty в пределах (cabinet, sku, month).

Заполняется sync_realization, читается backfill-таской которая
проставляет order_items.customer_price = weighted_cp +
customer_price_source = 'estimated_monthly' для NULL-записей этого SKU-месяца.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CustomerPriceMonthlyEstimate(Base):
    __tablename__ = "customer_price_monthly_estimate"

    cabinet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    sku: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    month: Mapped[date] = mapped_column(Date, primary_key=True)
    weighted_cp: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    weighted_sp: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    source_rows: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
