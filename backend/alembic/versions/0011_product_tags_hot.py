"""products.tags JSONB + is_hot bool — теги и «горячие» товары.

Юзер хочет единый справочник: категории (уже есть в category_id/name),
свободные теги (свои метки типа «хит», «сезон») и флаг «горячий».

Revision ID: 0011_product_tags_hot
Revises: 0010_stocks_pk_wh
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0011_product_tags_hot"
down_revision = "0010_stocks_pk_wh"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "tags",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "is_hot",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # индекс на is_hot для быстрого фильтра
    op.create_index("ix_products_is_hot", "products", ["is_hot"])


def downgrade() -> None:
    op.drop_index("ix_products_is_hot", table_name="products")
    op.drop_column("products", "is_hot")
    op.drop_column("products", "tags")
