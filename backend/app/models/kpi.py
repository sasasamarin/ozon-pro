"""KPI Target — план для /analytics/plan-vs-fact."""
from __future__ import annotations

import uuid
from datetime import date as date_cls

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class KPITarget(BaseModel):
    __tablename__ = "kpi_targets"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "period_from", "period_to", "metric", "cabinet_id",
            name="uq_kpi_targets_unique",
        ),
        Index("ix_kpi_targets_company", "company_id"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    period_from: Mapped[date_cls] = mapped_column(Date, nullable=False)
    period_to: Mapped[date_cls] = mapped_column(Date, nullable=False)
    metric: Mapped[str] = mapped_column(String(30), nullable=False)  # revenue/gross_profit/orders/aov/margin_pct
    target_value: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    cabinet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
