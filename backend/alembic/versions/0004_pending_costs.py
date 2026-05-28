"""pending_costs: себестоимость для SKU, которых ещё нет в products.

Юзер импортирует CSV до того как товар появился в Ozon (или товар архивный
с тегом который синк не покрывает). Сохраняем purchase_price + offer_id_lower
здесь, при появлении product с matching offer_id — синк перенесёт запись
в product_cost_history автоматически.

Revision ID: 0004_pending_costs
Revises: 0003_legacy_hypertables
"""
from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "0004_pending_costs"
down_revision = "0003_legacy_hypertables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_costs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        # offer_id хранится в lowercase для дешёвого LIKE/equals match
        sa.Column("offer_id_lower", sa.String(255), nullable=False),
        sa.Column("purchase_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("notes", sa.Text, nullable=True),
        sa.UniqueConstraint("user_id", "offer_id_lower", name="uq_pending_costs_user_offer"),
    )
    op.create_index(
        "ix_pending_costs_offer", "pending_costs", ["offer_id_lower"]
    )


def downgrade() -> None:
    op.drop_index("ix_pending_costs_offer", "pending_costs")
    op.drop_table("pending_costs")
