"""realization_reconciliation: авто-сверка модели Flowoi с отчётом Ozon.

Хранит итог сверки одного кабинета × год × месяц.
- total_payout_real — что показал Ozon в /v2/finance/realization
- total_payout_model — что считает наша модель из транзакций
- diff_pct — расхождение в %
- sku_breakdown — детальная разбивка по SKU (jsonb)

Revision ID: 0014_realiz_reconcile
Revises: 0013_oi_customer_price
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "0014_realiz_reconcile"
down_revision = "0013_oi_customer_price"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "realization_reconciliation",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("ozon_account_id", UUID(as_uuid=True),
                  sa.ForeignKey("ozon_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("total_revenue", sa.Numeric(15, 2), nullable=True),
        sa.Column("total_payout_real", sa.Numeric(15, 2), nullable=True),
        sa.Column("total_payout_model", sa.Numeric(15, 2), nullable=True),
        sa.Column("diff_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("sku_breakdown", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("ozon_account_id", "year", "month",
                            name="uq_realization_reconcile_acc_period"),
    )


def downgrade() -> None:
    op.drop_table("realization_reconciliation")
