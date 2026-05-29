"""ad_statistics PK must include product_id (ON CONFLICT fix).

Модель описывает PK (date, ozon_campaign_id, product_id), но в БД constraint
остался без product_id — из-за этого ON CONFLICT в sync_ads_statistics валился.

TimescaleDB разрешает менять PK, пока он содержит time-column (date).

Revision ID: 0009_ad_stats_pk
Revises: 0008_widen_ad_campaigns_state
"""
from __future__ import annotations

from alembic import op


revision = "0009_ad_stats_pk"
down_revision = "0008_widen_ad_campaigns_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE ad_statistics SET product_id = '00000000-0000-0000-0000-000000000000'::uuid "
        "WHERE product_id IS NULL"
    )
    op.execute("ALTER TABLE ad_statistics ALTER COLUMN product_id SET NOT NULL")
    op.execute("ALTER TABLE ad_statistics DROP CONSTRAINT IF EXISTS pk_ad_statistics")
    op.execute(
        "ALTER TABLE ad_statistics ADD CONSTRAINT pk_ad_statistics "
        "PRIMARY KEY (date, ozon_campaign_id, product_id)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE ad_statistics DROP CONSTRAINT IF EXISTS pk_ad_statistics")
    op.execute(
        "ALTER TABLE ad_statistics ADD CONSTRAINT pk_ad_statistics "
        "PRIMARY KEY (date, ozon_campaign_id)"
    )
