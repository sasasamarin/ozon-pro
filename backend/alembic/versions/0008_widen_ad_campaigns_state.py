"""widen ad_campaigns.state and campaign_type — Ozon Performance шлёт длинные ENUM-строки.

Ozon отдаёт state как `CAMPAIGN_STATE_RUNNING` (22 сим.), что не влезало в varchar(20)
и валило весь sync_all_ad_campaigns. Расширяем оба поля до varchar(64).

Revision ID: 0008_widen_ad_campaigns_state
Revises: 0007_kpi_targets
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0008_widen_ad_campaigns_state"
down_revision = "0007_kpi_targets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "ad_campaigns", "state",
        existing_type=sa.String(length=20),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.alter_column(
        "ad_campaigns", "campaign_type",
        existing_type=sa.String(length=30),
        type_=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "ad_campaigns", "campaign_type",
        existing_type=sa.String(length=64),
        type_=sa.String(length=30),
        existing_nullable=False,
    )
    op.alter_column(
        "ad_campaigns", "state",
        existing_type=sa.String(length=64),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
