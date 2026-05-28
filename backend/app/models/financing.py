"""
Финансовые продукты Ozon (займы, авансы, удержания).

- OzonFinancing            — открытый финансовый продукт
- OzonFinancingMovement    — каждое движение по нему (TimescaleDB hypertable)

ПРАВИЛО P&L:
- Тело долга НИКОГДА не в P&L
- P&L = Σ(movements where affects_pnl=true)  → только interest_charge
- Cashflow = Σ(movements where affects_cashflow=true)
- Долг = Σ(movements.affects_debt) по status in (active, repaying)
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModel


class FinancingProductType(str, Enum):
    ADVANCE_BEFORE_SALE = "advance_before_sale"
    EARLY_PAYOUT = "early_payout"
    LOAN_PURCHASE = "loan_purchase"
    LOAN_WORKING_CAPITAL = "loan_working_capital"
    COMMISSION_INSTALLMENT = "commission_installment"
    EXTERNAL_LOAN = "external_loan"


class FinancingStatus(str, Enum):
    ACTIVE = "active"
    REPAYING = "repaying"
    CLOSED = "closed"


class FinancingSource(str, Enum):
    OZON_API = "ozon_api"
    MANUAL = "manual"


class FinancingMovementType(str, Enum):
    DISBURSEMENT = "disbursement"
    REPAYMENT_PRINCIPAL = "repayment_principal"
    INTEREST_CHARGE = "interest_charge"
    WITHHOLDING = "withholding"


class OzonFinancing(BaseModel):
    __tablename__ = "ozon_financing"
    __table_args__ = (Index("ix_ozon_financing_user", "user_id"),)

    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ozon_accounts.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    product_type: Mapped[str] = mapped_column(String(40), nullable=False)
    principal: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    interest_rate: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=FinancingStatus.ACTIVE.value, nullable=False
    )
    source: Mapped[str] = mapped_column(
        String(20), default=FinancingSource.MANUAL.value, nullable=False
    )
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)


# ============================================================
# HYPERTABLE: ozon_financing_movements
# ============================================================


class OzonFinancingMovement(Base):
    """Одно движение по финансовому продукту."""

    __tablename__ = "ozon_financing_movements"
    __table_args__ = (Index("ix_financing_movements_fin", "financing_id"),)

    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    financing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_financing.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    # Suffix для уникальности при множественных движениях в ту же секунду
    seq: Mapped[int] = mapped_column(primary_key=True, nullable=False, default=0)

    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    affects_pnl: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    affects_cashflow: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    affects_debt: Mapped[float] = mapped_column(
        Numeric(14, 2), default=0, server_default="0", nullable=False
    )

    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
