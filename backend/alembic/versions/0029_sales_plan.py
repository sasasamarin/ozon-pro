"""Sales plan tables: sales_plan, sales_plan_item, sales_plan_daily, plan_kpi.

Revision ID: 0029_sales_plan
Revises: 0028_premium_endpoints
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0029_sales_plan"
down_revision = "0028_premium_endpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sales_plan",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_ref", sa.String(), nullable=True),
        sa.Column("metric_code", sa.String(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("analysis_start", sa.Date(), nullable=True),
        sa.Column("analysis_end", sa.Date(), nullable=True),
        sa.Column("base_forecast", sa.Numeric(), nullable=True),
        sa.Column("target_value", sa.Numeric(), nullable=True),
        sa.Column("distribution_mode", sa.String(), nullable=False),
        sa.Column("source_pref", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="user"),
        sa.CheckConstraint(
            "scope_type IN ('company','cabinet','category','group','glue','sku')",
            name="ck_sales_plan_scope_type",
        ),
        sa.CheckConstraint(
            "distribution_mode IN ('proportional','manual','seasonal')",
            name="ck_sales_plan_distribution_mode",
        ),
        sa.CheckConstraint(
            "source_pref IN ('operational','official')",
            name="ck_sales_plan_source_pref",
        ),
    )

    op.create_table(
        "sales_plan_item",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(), nullable=True),
        sa.Column("glue_id", sa.Integer(), nullable=True),
        sa.Column("analysis_value", sa.Numeric(), nullable=True),
        sa.Column("share_pct", sa.Numeric(), nullable=True),
        sa.Column("plan_value", sa.Numeric(), nullable=True),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(["plan_id"], ["sales_plan.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "sales_plan_daily",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plan_item_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("plan_value", sa.Numeric(), nullable=True),
        sa.Column("season_weight", sa.Numeric(), nullable=True),
        sa.ForeignKeyConstraint(
            ["plan_item_id"], ["sales_plan_item.id"], ondelete="CASCADE"
        ),
    )

    op.create_table(
        "plan_kpi",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("manager_id", sa.Integer(), nullable=True),
        sa.Column("metric_code", sa.String(), nullable=False),
        sa.Column("target_value", sa.Numeric(), nullable=True),
        sa.Column("bonus_rule", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["plan_id"], ["sales_plan.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("plan_kpi")
    op.drop_table("sales_plan_daily")
    op.drop_table("sales_plan_item")
    op.drop_table("sales_plan")
