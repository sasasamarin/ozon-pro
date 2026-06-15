"""ad_product_daily: per-SKU статистика рекламы «Оплата за клик» по дням.

Revision ID: 0036_ad_product_daily
Revises: 0035_member_modules

Отдельная таблица (не ad_statistics), чтобы per-SKU не двоил campaign-level
расход в безфильтровых суммах. Чистый CREATE TABLE — существующие данные не
затрагиваются.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "0036_ad_product_daily"
down_revision = "0035_member_modules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ad_product_daily",
        sa.Column("date", sa.Date(), primary_key=True, nullable=False),
        sa.Column("ozon_account_id", UUID(as_uuid=True),
                  sa.ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
                  primary_key=True, nullable=False),
        sa.Column("ozon_campaign_id", sa.String(50), primary_key=True, nullable=False),
        sa.Column("sku", sa.String(50), primary_key=True, nullable=False),
        sa.Column("product_id", UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("price", sa.Numeric(14, 2), nullable=True),
        sa.Column("views", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("clicks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("to_cart", sa.Integer(), server_default="0", nullable=False),
        sa.Column("avg_cpc", sa.Numeric(14, 2), nullable=True),
        sa.Column("spend", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("orders", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sales", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("model_orders", sa.Integer(), server_default="0", nullable=False),
        sa.Column("model_sales", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("ctr", sa.Numeric(7, 4), nullable=True),
        sa.Column("drr", sa.Numeric(7, 4), nullable=True),
        sa.Column("raw_data", JSON, server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ad_product_daily_account_date", "ad_product_daily",
                    ["ozon_account_id", "date"])
    op.create_index("ix_ad_product_daily_product", "ad_product_daily", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_ad_product_daily_product", table_name="ad_product_daily")
    op.drop_index("ix_ad_product_daily_account_date", table_name="ad_product_daily")
    op.drop_table("ad_product_daily")
