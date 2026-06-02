"""Premium Plus endpoints: product_queries_daily + realization_daily.

- product_queries_daily: /v1/analytics/product-queries — семантика товара
  (уникальные юзеры из поиска, позиция, конверсия, GMV).
- realization_daily: /v1/finance/realization/by-day — посуточная реализация
  (точная выручка/qty по каждому дню за последние 32 дня).

Revision ID: 0028_premium_endpoints
Revises: 0027_analytics_hits_view
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0028_premium_endpoints"
down_revision = "0027_analytics_hits_view"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # === product_queries_daily — семантика товара ===
    # ВАЖНО: /v1/analytics/product-queries отдаёт АГРЕГАТ за период, не
    # подневно. Запрашиваем по 1 дню → сохраняем snapshot date=date.
    op.create_table(
        "product_queries_daily",
        sa.Column("cabinet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("offer_id", sa.String(255), nullable=True),
        sa.Column("unique_search_users", sa.Integer(), nullable=True,
                  comment="Уникальные юзеры, видевшие товар в поиске"),
        sa.Column("unique_view_users", sa.Integer(), nullable=True,
                  comment="Уникальные юзеры на карточке"),
        sa.Column("position", sa.Numeric(8, 2), nullable=True,
                  comment="Средняя позиция в поиске"),
        sa.Column("view_conversion", sa.Numeric(8, 4), nullable=True,
                  comment="Конверсия из поиска в карточку, %"),
        sa.Column("gmv", sa.Numeric(15, 2), nullable=True,
                  comment="Выручка с показов в поиске за период"),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("cabinet_id", "sku", "date",
                                name="pk_product_queries_daily"),
        sa.ForeignKeyConstraint(["cabinet_id"], ["ozon_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_pq_date", "product_queries_daily", ["date"])
    op.create_index("ix_pq_product_date", "product_queries_daily", ["product_id", "date"])

    # === realization_daily — посуточная реализация ===
    op.create_table(
        "realization_daily",
        sa.Column("cabinet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.BigInteger(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("offer_id", sa.String(255), nullable=True),
        sa.Column("qty_sold", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("qty_returned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("weighted_cp", sa.Numeric(15, 2), nullable=True,
                  comment="Средняя цена покупателя (weighted by qty)"),
        sa.Column("weighted_sp", sa.Numeric(15, 2), nullable=True,
                  comment="Средняя цена продавца (begin)"),
        sa.Column("sum_bonus", sa.Numeric(15, 2), nullable=False, server_default="0",
                  comment="СПП-компенсация Ozon продавцу"),
        sa.Column("sum_fee", sa.Numeric(15, 2), nullable=False, server_default="0",
                  comment="Комиссия Ozon"),
        sa.Column("rows_aggregated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("synced_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("cabinet_id", "sku", "day", name="pk_realization_daily"),
        sa.ForeignKeyConstraint(["cabinet_id"], ["ozon_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_rd_day", "realization_daily", ["day"])
    op.create_index("ix_rd_product_day", "realization_daily", ["product_id", "day"])


def downgrade() -> None:
    op.drop_table("realization_daily")
    op.drop_table("product_queries_daily")
