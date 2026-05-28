"""
Три представления денег:

- FinancialReport          — официальный отчёт Ozon (async flow)
- AccountBalanceSnapshot   — снимок баланса кабинета (hypertable)
- Reconciliation           — автосверка трёх источников
- ManualReconciliation     — обратная (ручная) сверка против файла Ozon
- ManualReconciliationLine — построчное сравнение метрик
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModel


class FinancialReportType(str, Enum):
    REALIZATION = "realization"
    FINANCE_SUMMARY = "finance_summary"
    MUTUAL_SETTLEMENT = "mutual_settlement"


class FinancialReportStatus(str, Enum):
    REQUESTED = "requested"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ReconciliationStatus(str, Enum):
    MATCHED = "matched"
    MINOR_DIFF = "minor_diff"
    MAJOR_DIFF = "major_diff"


class ManualReconciliationFileType(str, Enum):
    OZON_REALIZATION_XLSX = "ozon_realization_xlsx"
    OZON_FINANCE_XLSX = "ozon_finance_xlsx"
    BANK_STATEMENT = "bank_statement"
    CUSTOM = "custom"


class ManualReconciliationStatus(str, Enum):
    MATCHED = "matched"
    HAS_WARNINGS = "has_warnings"
    HAS_ERRORS = "has_errors"


class ReconciliationLineStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


class FinancialReport(BaseModel):
    """Запрошенный у Ozon финансовый отчёт. Async flow: request → poll → download."""

    __tablename__ = "financial_reports"
    __table_args__ = (
        Index("ix_financial_reports_user", "user_id"),
        Index("ix_financial_reports_account_period", "ozon_account_id", "period_from", "period_to"),
    )

    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ozon_accounts.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    report_type: Mapped[str] = mapped_column(String(30), nullable=False)
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=FinancialReportStatus.REQUESTED.value, nullable=False
    )

    ozon_report_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    total_accrued: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    total_withheld: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    total_to_payout: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    raw_file_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)

    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ============================================================
# HYPERTABLE: account_balance_snapshots
# ============================================================


class AccountBalanceSnapshot(Base):
    """Снимок баланса кабинета — что Ozon показывает в личном кабинете."""

    __tablename__ = "account_balance_snapshots"
    __table_args__ = (
        Index("ix_balance_snapshots_user_time", "user_id", "time"),
    )

    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    available_now: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    pending: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    withheld_total: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    next_payout_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_payout_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)


class Reconciliation(BaseModel):
    """Автосверка трёх источников: realtime / report / balance."""

    __tablename__ = "reconciliation"
    __table_args__ = (
        Index("ix_reconciliation_user", "user_id"),
        Index("ix_reconciliation_account_period", "ozon_account_id", "period_from", "period_to"),
    )

    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ozon_accounts.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)

    realtime_sum: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    report_sum: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    balance_sum: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    delta_rt_report: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    delta_report_balance: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), default=ReconciliationStatus.MATCHED.value, nullable=False
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ManualReconciliation(BaseModel):
    """Обратная (ручная) сверка против файла Ozon Realization/Finance."""

    __tablename__ = "manual_reconciliation"
    __table_args__ = (
        Index("ix_manual_reconciliation_user", "user_id"),
        Index("ix_manual_reconciliation_account_period", "ozon_account_id", "period_from", "period_to"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ozon_accounts.id", ondelete="CASCADE"), nullable=False
    )

    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)

    uploaded_file_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_file_type: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Flowoi-расчёт
    flowoi_revenue: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    flowoi_commission: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    flowoi_logistics: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    flowoi_ads: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    flowoi_cogs: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    flowoi_net_profit: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    # Ozon-цифры из файла
    ozon_revenue: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    ozon_commission: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    ozon_logistics: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    ozon_payout: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    comparison_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    overall_status: Mapped[str] = mapped_column(
        String(20), default=ManualReconciliationStatus.MATCHED.value, nullable=False
    )

    checked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ManualReconciliationLine(BaseModel):
    """Одна строка сравнения метрики Flowoi vs Ozon."""

    __tablename__ = "manual_reconciliation_lines"
    __table_args__ = (Index("ix_manual_recon_lines_parent", "reconciliation_id"),)

    reconciliation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("manual_reconciliation.id", ondelete="CASCADE"),
        nullable=False,
    )

    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    flowoi_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    ozon_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    delta: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    delta_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), default=ReconciliationLineStatus.OK.value, nullable=False
    )
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
