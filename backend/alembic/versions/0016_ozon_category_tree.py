"""ozon_category_tree: иерархия категорий Ozon с предками для UI.

Загружается из /v1/description-category/tree (один раз глобально, не per-account).
Используется для разворачиваемого дерева на /products/categories и для
агрегации продаж по уровням ветки.

Revision ID: 0016_ozon_category_tree
Revises: 0015_company_tax
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_ozon_category_tree"
down_revision = "0015_company_tax"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ozon_category_tree",
        sa.Column("ozon_id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("full_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_type", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["ozon_category_tree.ozon_id"],
            name="fk_category_tree_parent", ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_ozon_category_tree_parent_id", "ozon_category_tree", ["parent_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ozon_category_tree_parent_id", table_name="ozon_category_tree")
    op.drop_table("ozon_category_tree")
