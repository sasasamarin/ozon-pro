"""Расширяем Numeric(5,4) → Numeric(10,4) для conv_tocart_* в analytics_daily.

Ozon /v1/analytics/data возвращает conv_tocart_* значения, которые
periodically превышают 9.9999 (max для Numeric(5,4)) → backfill валился с
NumericValueOutOfRangeError. Numeric(10,4) даёт запас до 999999.9999.

Revision ID: 0005_widen_analytics_conv
Revises: 0004_pending_costs
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0005_widen_analytics_conv"
down_revision = "0004_pending_costs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Numeric(10,4) даёт запас при сохранении точности 4 знаков после запятой
    op.alter_column(
        "analytics_daily",
        "conv_tocart_search",
        type_=sa.Numeric(10, 4),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
    )
    op.alter_column(
        "analytics_daily",
        "conv_tocart_pdp",
        type_=sa.Numeric(10, 4),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
    )


def downgrade() -> None:
    op.alter_column(
        "analytics_daily", "conv_tocart_search", type_=sa.Numeric(5, 4),
        existing_nullable=False, existing_server_default=sa.text("0"),
    )
    op.alter_column(
        "analytics_daily", "conv_tocart_pdp", type_=sa.Numeric(5, 4),
        existing_nullable=False, existing_server_default=sa.text("0"),
    )
