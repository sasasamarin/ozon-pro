"""Sales plan: статус (draft|active|archived).

Revision ID: 0033_sales_plan_status
Revises: 0032_sales_plan
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_sales_plan_status"
down_revision = "0032_sales_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sales_plan",
        sa.Column("status", sa.String(20), nullable=False, server_default="active"))
    op.create_index("ix_sales_plan_status", "sales_plan", ["company_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_sales_plan_status", table_name="sales_plan")
    op.drop_column("sales_plan", "status")
