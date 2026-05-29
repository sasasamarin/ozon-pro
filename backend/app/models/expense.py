"""External (внутренний) расход бизнеса: зарплата, аренда, налог."""
from __future__ import annotations

import uuid
from datetime import date as date_cls, datetime
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class ExpenseCategory(str, Enum):
    SALARY = "salary"
    RENT = "rent"
    TAX = "tax"
    SOFTWARE = "software"
    EQUIPMENT = "equipment"
    LEGAL = "legal"
    OTHER = "other"


class ExternalExpense(BaseModel):
    __tablename__ = "external_expenses"
    __table_args__ = (
        Index("ix_external_expenses_user_date", "user_id", "date"),
        Index("ix_external_expenses_category", "category"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    date: Mapped[date_cls] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
