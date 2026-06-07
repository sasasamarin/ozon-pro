"""Change sales_plan.company_id from int to UUID.

Таблица sales_plan.company_id была создана как int, но в системе
company_id повсюду UUID (User.company_id, Company.id).
Таблица пустая — data migration не требуется.

Revision ID: 0030_sales_plan_company_uuid
Revises: 0029_sales_plan
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0030_sales_plan_company_uuid"
down_revision = "0029_sales_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "sales_plan",
        "company_id",
        type_=postgresql.UUID(as_uuid=True),
        postgresql_using="gen_random_uuid()",
        existing_nullable=False,
        existing_type=sa.Integer(),
    )


def downgrade() -> None:
    op.alter_column(
        "sales_plan",
        "company_id",
        type_=sa.Integer(),
        postgresql_using="0",
        existing_nullable=False,
        existing_type=postgresql.UUID(as_uuid=True),
    )
