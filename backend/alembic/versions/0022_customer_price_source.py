"""customer_price_source + customer_price_monthly_estimate (дерайв из realization).

#105 — для старых месяцев (>90 дней, posting/fbo/get не отдаёт) customer_price
дерайвится как weighted_avg по qty из /v2/finance/realization
(delivery_commission.price_per_instance).

Источник записывается в order_items.customer_price_source = 'estimated_monthly'.
Точные данные с posting/fbo/get имеют source = NULL (по-умолчанию) или 'api'.

Revision ID: 0022_customer_price_source
Revises: 0021_loans
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_customer_price_source"
down_revision = "0021_loans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "order_items",
        sa.Column("customer_price_source", sa.String(30), nullable=True,
                  comment="NULL/api = точный из posting/fbo/get; "
                          "'estimated_monthly' = weighted avg по qty из realization API"),
    )

    op.create_table(
        "customer_price_monthly_estimate",
        sa.Column("cabinet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.BigInteger(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False,
                  comment="Первый день месяца"),
        sa.Column("weighted_cp", sa.Numeric(15, 2), nullable=False,
                  comment="Σ(price_per_instance × qty) / Σ qty"),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("weighted_sp", sa.Numeric(15, 2), nullable=True,
                  comment="seller_price среднее для сверки"),
        sa.Column("source_rows", sa.Integer(), nullable=False, server_default="0",
                  comment="Сколько строк realization агрегировано"),
        sa.Column("computed_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("cabinet_id", "sku", "month",
                                name="pk_customer_price_monthly_estimate"),
        sa.ForeignKeyConstraint(["cabinet_id"], ["ozon_accounts.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("customer_price_monthly_estimate")
    op.drop_column("order_items", "customer_price_source")
