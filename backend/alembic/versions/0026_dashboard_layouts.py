"""dashboard_layouts — per-user раскладка карточек на Дашборде.

Revision ID: 0026_dashboard_layouts
Revises: 0025_product_stats
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026_dashboard_layouts"
down_revision = "0025_product_stats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dashboard_layouts",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False, server_default="cabinet",
                  comment="cabinet | product (раскладка для какого экрана)"),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column("cards", postgresql.JSONB, nullable=False, server_default="[]",
                  comment="[{id, title, chartType, metrics:[{key, axis, color}]}]"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "scope", name="uq_layout_user_scope"),
    )


def downgrade() -> None:
    op.drop_table("dashboard_layouts")
