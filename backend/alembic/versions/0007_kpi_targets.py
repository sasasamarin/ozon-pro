"""kpi_targets — целевые показатели для /analytics/plan-vs-fact.

Revision ID: 0007_kpi_targets
Revises: 0006_external_expenses
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "0007_kpi_targets"
down_revision = "0006_external_expenses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kpi_targets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("period_from", sa.Date, nullable=False),
        sa.Column("period_to", sa.Date, nullable=False),
        sa.Column("metric", sa.String(30), nullable=False),
        # revenue / gross_profit / orders / aov / margin_pct
        sa.Column("target_value", sa.Numeric(14, 2), nullable=False),
        sa.Column("cabinet_id", UUID(as_uuid=True),
                  sa.ForeignKey("ozon_accounts.id", ondelete="CASCADE"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "period_from", "period_to", "metric",
                            "cabinet_id", name="uq_kpi_targets_unique"),
    )
    op.create_index("ix_kpi_targets_company", "kpi_targets", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_kpi_targets_company", "kpi_targets")
    op.drop_table("kpi_targets")
