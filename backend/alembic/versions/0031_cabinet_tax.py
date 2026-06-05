"""Per-cabinet tax overrides: режим + ставка + НДС + возвратность.

Revision ID: 0031_cabinet_tax
Revises: 0030_commission_history
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031_cabinet_tax"
down_revision = "0030_commission_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ozon_accounts",
        sa.Column("tax_regime", sa.String(30), nullable=True))
    op.add_column("ozon_accounts",
        sa.Column("tax_rate_pct", sa.Numeric(5, 2), nullable=True))
    op.add_column("ozon_accounts",
        sa.Column("vat_rate_pct", sa.Numeric(5, 2), nullable=True))
    op.add_column("ozon_accounts",
        sa.Column("vat_refundable", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("ozon_accounts",
        sa.Column("tax_region_note", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("ozon_accounts", "tax_region_note")
    op.drop_column("ozon_accounts", "vat_refundable")
    op.drop_column("ozon_accounts", "vat_rate_pct")
    op.drop_column("ozon_accounts", "tax_rate_pct")
    op.drop_column("ozon_accounts", "tax_regime")
