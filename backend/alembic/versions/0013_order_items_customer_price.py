"""order_items: + customer_price (то что физически платит покупатель с СПП).

В Ozon API customer_price отдаётся per-posting в /v2/posting/fbo/get
(в financial_data.products[].customer_price). Это маркетинговый слой —
ИНДИВИДУАЛЬНАЯ цена для каждого покупателя (зависит от Premium/Ozon-Карты/баллов).
Не влияет на финансы продавца (accruals_for_sale = selling_price), но
является драйвером спроса.

Revision ID: 0013_oi_customer_price
Revises: 0012_product_commissions
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0013_oi_customer_price"
down_revision = "0012_product_commissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "order_items",
        sa.Column("customer_price", sa.Numeric(15, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("order_items", "customer_price")
