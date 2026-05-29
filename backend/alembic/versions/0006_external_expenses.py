"""external_expenses: внутренние расходы бизнеса (зарплаты/аренда/налоги).

Revision ID: 0006_external_expenses
Revises: 0005_widen_analytics_conv
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "0006_external_expenses"
down_revision = "0005_widen_analytics_conv"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_expenses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("recurring", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_external_expenses_user_date", "external_expenses",
                    ["user_id", "date"])
    op.create_index("ix_external_expenses_category", "external_expenses", ["category"])


def downgrade() -> None:
    op.drop_index("ix_external_expenses_category", "external_expenses")
    op.drop_index("ix_external_expenses_user_date", "external_expenses")
    op.drop_table("external_expenses")
