"""Convert transactions / stocks / analytics_daily to TimescaleDB hypertables.

These three tables were defined as hypertables in the models from Phase 1 but
were never actually converted on the managed DB (init_hypertables.py only
made it partway through during initial setup). Phase 1 syncs persisted to
them as regular tables, which works but loses chunking + compression.

Tables are still empty in production → migrate_data=>TRUE is a no-op.

Revision ID: 0003_legacy_hypertables
Revises: 2540a3b19862
Create Date: 2026-05-28
"""
from __future__ import annotations

from alembic import op

revision = "0003_legacy_hypertables"
down_revision = "2540a3b19862"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, time_col, interval in (
        ("transactions", "time", "30 days"),
        ("stocks", "time", "7 days"),
        ("analytics_daily", "date", "30 days"),
    ):
        op.execute(
            f"SELECT create_hypertable("
            f"'{table}', '{time_col}', "
            f"chunk_time_interval => INTERVAL '{interval}', "
            f"migrate_data => TRUE, "
            f"if_not_exists => TRUE)"
        )


def downgrade() -> None:
    # TimescaleDB не поддерживает «обратное превращение» hypertable в обычную
    # таблицу одной командой — это потребовало бы пересоздания таблицы с
    # копированием данных. Downgrade оставляем no-op (откат осмысленно
    # делается только восстановлением из бэкапа).
    pass
