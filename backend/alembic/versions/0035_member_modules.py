"""CompanyMember: allowed_modules JSONB.

Revision ID: 0035_member_modules
Revises: 0034_sales_plan_template
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0035_member_modules"
down_revision = "0034_sales_plan_template"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("company_members",
        sa.Column("allowed_modules", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("company_members", "allowed_modules")
