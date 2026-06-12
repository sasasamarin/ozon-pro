"""Change plan_kpi.manager_id from Integer to Text for UUID storage.

manager_id был создан как int, но users.id — UUID. Таблица пустая — data
migration не требуется.

Revision ID: 0031_plan_kpi_manager_text
Revises: 0030_sales_plan_company_uuid
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031_plan_kpi_manager_text"
down_revision = "0030_sales_plan_company_uuid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "plan_kpi",
        "manager_id",
        existing_type=sa.Integer(),
        type_=sa.Text(),
        nullable=True,
        postgresql_using="manager_id::text",
    )


def downgrade() -> None:
    op.alter_column(
        "plan_kpi",
        "manager_id",
        existing_type=sa.Text(),
        type_=sa.Integer(),
        nullable=True,
        postgresql_using="manager_id::integer",
    )
