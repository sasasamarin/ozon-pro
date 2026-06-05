"""План продаж — sales_plan + items + daily + plan_kpi.

Revision ID: 0032_sales_plan
Revises: 0031_cabinet_tax
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0032_sales_plan"
down_revision = "0031_cabinet_tax"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # === sales_plan: один план с целью + параметрами прогноза ===
    op.create_table(
        "sales_plan",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        # scope: company | cabinet | category | group | glue | sku
        sa.Column("scope_type", sa.String(20), nullable=False),
        sa.Column("scope_ref", sa.String(100), nullable=True),
        sa.Column("metric_code", sa.String(40), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("analysis_start", sa.Date, nullable=False),
        sa.Column("analysis_end", sa.Date, nullable=False),
        sa.Column("base_forecast", sa.Numeric(16, 2), nullable=True),
        sa.Column("target_value", sa.Numeric(16, 2), nullable=False),
        sa.Column("distribution_mode", sa.String(20),
                  nullable=False, server_default="proportional"),
        sa.Column("source_pref", sa.String(20),
                  nullable=False, server_default="operational"),
        sa.Column("source", sa.String(20), nullable=False, server_default="user"),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sales_plan_company_period",
                    "sales_plan", ["company_id", "period_start"])

    # === sales_plan_item: SKU-разбиение плана ===
    op.create_table(
        "sales_plan_item",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sales_plan.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sku", sa.String(100), nullable=True),
        sa.Column("glue_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("analysis_value", sa.Numeric(16, 2),
                  nullable=False, server_default="0"),
        sa.Column("share_pct", sa.Numeric(8, 4),
                  nullable=False, server_default="0"),
        sa.Column("plan_value", sa.Numeric(16, 2),
                  nullable=False, server_default="0"),
        sa.Column("is_locked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sales_plan_item_plan",
                    "sales_plan_item", ["plan_id"])

    # === sales_plan_daily: разбиение SKU плана по дням ===
    op.create_table(
        "sales_plan_daily",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("plan_item_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sales_plan_item.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("plan_value", sa.Numeric(16, 2),
                  nullable=False, server_default="0"),
        sa.Column("season_weight", sa.Numeric(8, 6),
                  nullable=False, server_default="0"),
        sa.UniqueConstraint("plan_item_id", "date", name="uq_plan_daily_item_date"),
    )
    op.create_index("ix_plan_daily_date",
                    "sales_plan_daily", ["date"])

    # === plan_kpi: KPI менеджмента, привязан к плану ===
    op.create_table(
        "plan_kpi",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sales_plan.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manager_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("manager_name", sa.String(255), nullable=True),
        sa.Column("metric_code", sa.String(40), nullable=False),
        sa.Column("target_value", sa.Numeric(16, 2), nullable=False),
        # bonus_rule jsonb: {"model": "A"|"B", "pct_of_net": 5, "thresholds": [...]}
        sa.Column("bonus_rule", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_plan_kpi_plan",
                    "plan_kpi", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_plan_kpi_plan", table_name="plan_kpi")
    op.drop_table("plan_kpi")
    op.drop_index("ix_plan_daily_date", table_name="sales_plan_daily")
    op.drop_table("sales_plan_daily")
    op.drop_index("ix_sales_plan_item_plan", table_name="sales_plan_item")
    op.drop_table("sales_plan_item")
    op.drop_index("ix_sales_plan_company_period", table_name="sales_plan")
    op.drop_table("sales_plan")
