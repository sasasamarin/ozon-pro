"""products: + комиссии и логистика Ozon per-товар (для точной чистой маржи).

Ozon в /v5/product/info/prices отдаёт по каждому товару точные:
- sales_percent_fbo/fbs (комиссия Ozon, 40-47%)
- volume_weight (литры, для логистики)
- acquiring_amount (эквайринг ₽)
- fbo_deliv_to_customer / fbo_direct_flow_trans_* / fbo_return_flow_amount

Раньше мы это не сохраняли, маржу считали эвристикой −32.5 п.п.
Реальная комиссия ~40% → чистая маржа была завышена.

Revision ID: 0012_product_commissions
Revises: 0011_product_tags_hot
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0012_product_commissions"
down_revision = "0011_product_tags_hot"
branch_labels = None
depends_on = None


COLUMNS = [
    ("volume_weight",             sa.Numeric(8, 3)),
    ("acquiring_amount",          sa.Numeric(12, 2)),
    ("sales_percent_fbo",         sa.Numeric(5, 2)),
    ("sales_percent_fbs",         sa.Numeric(5, 2)),
    ("fbo_deliv_to_customer",     sa.Numeric(12, 2)),
    ("fbo_direct_flow_trans_min", sa.Numeric(12, 2)),
    ("fbo_direct_flow_trans_max", sa.Numeric(12, 2)),
    ("fbo_return_flow_amount",    sa.Numeric(12, 2)),
]


def upgrade() -> None:
    for name, typ in COLUMNS:
        op.add_column("products", sa.Column(name, typ, nullable=True))
    op.add_column("products", sa.Column("commissions_raw", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "commissions_raw")
    for name, _ in reversed(COLUMNS):
        op.drop_column("products", name)
