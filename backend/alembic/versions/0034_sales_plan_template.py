"""Sales plan: шаблоны (is_template, cabinet_ids), ручная корректировка, заметки шага.

Revision ID: 0034_sales_plan_template
Revises: 0033_sales_plan_status
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034_sales_plan_template"
down_revision = "0033_sales_plan_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Шаблон vs обычный план
    op.add_column("sales_plan",
        sa.Column("is_template", sa.Boolean,
                  nullable=False, server_default="false"))
    # cabinet_ids шаблона (JSONB список UUID) — какие кабинеты покрывает
    op.add_column("sales_plan",
        sa.Column("template_cabinet_ids", postgresql.JSONB, nullable=True))
    # Ручная корректировка итогов (заметка + сумма)
    op.add_column("sales_plan",
        sa.Column("manual_adjustment", sa.Numeric(16, 2),
                  nullable=False, server_default="0"))
    op.add_column("sales_plan",
        sa.Column("workspace_notes", sa.Text, nullable=True))
    # rollover: после закрытия плана — ссылка на следующий, если auto-rolled
    op.add_column("sales_plan",
        sa.Column("rolled_from_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.create_index("ix_sales_plan_template", "sales_plan", ["company_id", "is_template"])


def downgrade() -> None:
    op.drop_index("ix_sales_plan_template", table_name="sales_plan")
    op.drop_column("sales_plan", "rolled_from_id")
    op.drop_column("sales_plan", "workspace_notes")
    op.drop_column("sales_plan", "manual_adjustment")
    op.drop_column("sales_plan", "template_cabinet_ids")
    op.drop_column("sales_plan", "is_template")
