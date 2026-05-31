"""sync_state: курсор синхронизации (cabinet, endpoint).

Возобновляемая синхра — после падения продолжаем с последнего успешного дня,
а не гоняем весь диапазон с нуля.

Revision ID: 0017_sync_state
Revises: 0016_ozon_category_tree
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_sync_state"
down_revision = "0016_ozon_category_tree"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_state",
        sa.Column("cabinet_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(100), nullable=False),
        sa.Column("last_cursor", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("cabinet_id", "endpoint", name="pk_sync_state"),
        sa.ForeignKeyConstraint(
            ["cabinet_id"], ["ozon_accounts.id"],
            name="fk_sync_state_cabinet", ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("sync_state")
