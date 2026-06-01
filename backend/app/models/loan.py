"""
Настоящие кредиты/займы продавца — учёт вручную.

Главный принцип:
- Тело займа (principal_part) НИКОГДА не в P&L. Только в ДДС.
- Расход в P&L — interest_part + fee_part.

Заём от банка (Ozon.Invest или внешний) через Seller API не отдаётся.
Юзер заводит договор, Flowoi строит график платежей (аннуитет/диффер.),
либо юзер вносит факты платежей вручную.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Loan(Base):
    __tablename__ = "loans"
    __table_args__ = (
        Index("ix_loans_company", "company_id"),
        Index("ix_loans_status_issued", "status", "issued_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    cabinet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    lender: Mapped[str | None] = mapped_column(Text, nullable=True)
    principal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    issued_at: Mapped[date] = mapped_column(Date, nullable=False)
    term_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schedule_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="annuity"
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    payments: Mapped[list["LoanPayment"]] = relationship(
        back_populates="loan", cascade="all, delete-orphan",
        order_by="LoanPayment.seq",
    )


class LoanPayment(Base):
    __tablename__ = "loan_payments"
    __table_args__ = (
        UniqueConstraint("loan_id", "seq", name="uq_loan_payments_loan_seq"),
        Index("ix_loan_payments_company_date", "company_id", "pay_date"),
        Index("ix_loan_payments_loan_date", "loan_id", "pay_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    loan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("loans.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    pay_date: Mapped[date] = mapped_column(Date, nullable=False)
    principal_part: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    interest_part: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    fee_part: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    is_paid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    paid_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="schedule")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    loan: Mapped[Loan] = relationship(back_populates="payments")
