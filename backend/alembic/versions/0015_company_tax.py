"""companies: + tax_regime/tax_rate_pct/vat_rate_pct.

Без налогового режима «чистая прибыль» = валовая (без вычета налога), что
сильно расходится с реальностью. Применяется в P&L/Cashflow/Экономика.

По умолчанию УСН Доходы 6% — самый частый режим для селлеров маркетплейса.

Revision ID: 0015_company_tax
Revises: 0014_realiz_reconcile
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0015_company_tax"
down_revision = "0014_realiz_reconcile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column(
        "tax_regime", sa.String(20),
        server_default="usn_income", nullable=False,
    ))
    op.add_column("companies", sa.Column(
        "tax_rate_pct", sa.Numeric(5, 2),
        server_default="6.0", nullable=False,
    ))
    op.add_column("companies", sa.Column(
        "vat_rate_pct", sa.Numeric(5, 2), nullable=True,
    ))


def downgrade() -> None:
    op.drop_column("companies", "vat_rate_pct")
    op.drop_column("companies", "tax_rate_pct")
    op.drop_column("companies", "tax_regime")
