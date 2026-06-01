"""metric_templates + day_markers — для «Статистики товара».

Revision ID: 0025_product_stats
Revises: 0024_supplies_extra
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0025_product_stats"
down_revision = "0024_supplies_extra"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metric_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("metrics", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_metric_templates_company", "metric_templates", ["company_id"])

    op.create_table(
        "day_markers",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cabinet_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("marker_date", sa.Date(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cabinet_id"], ["ozon_accounts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_day_markers_product_date", "day_markers",
                    ["product_id", "marker_date"])
    op.create_index("ix_day_markers_company_date", "day_markers",
                    ["company_id", "marker_date"])


def downgrade() -> None:
    op.drop_table("day_markers")
    op.drop_table("metric_templates")
