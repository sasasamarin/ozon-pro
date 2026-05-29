"""ad_statistics PK должен включать product_id — иначе ON CONFLICT в sync_ads валится.

В модели (app.models.ad.AdStatistics) product_id был добавлен в составной PK,
но в БД он остался индексом без UNIQUE. Из-за этого upsert через
ON CONFLICT (date, ozon_campaign_id, product_id) падал с
InvalidColumnReferenceError.

TimescaleDB разрешает менять PK, пока он содержит time-column (date) — ок.

Revision ID: 0009_ad_statistics_pk_with_product
Revises: 0008_widen_ad_campaigns_state
"""
from __future__ import annotations

from alembic import op


revision = "0009_ad_statistics_pk_with_product"
down_revision = "0008_widen_ad_campaigns_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL product_id будут заменены на NIL UUID — на момент миграции таблица пуста,
    # но защитимся на случай локальных бэкапов.
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
