"""Snapshot комиссий per-SKU per-day (для COMMISSION_CHANGE алерта).

Revision ID: 0030_commission_history
Revises: 0029_ai_chat_sessions
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0030_commission_history"
down_revision = "0029_ai_chat_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_commission_history",
        sa.Column("product_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="CASCADE"),
                  primary_key=True, nullable=False),
        sa.Column("snapshot_date", sa.Date, primary_key=True, nullable=False),
        sa.Column("sales_percent_fbo", sa.Numeric(5, 2), nullable=True),
        sa.Column("sales_percent_fbs", sa.Numeric(5, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pch_date", "product_commission_history", ["snapshot_date"])


def downgrade() -> None:
    op.drop_index("ix_pch_date", table_name="product_commission_history")
    op.drop_table("product_commission_history")
