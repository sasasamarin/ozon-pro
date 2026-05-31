"""sync_state: + last_synced_from (нижняя граница окна).

last_cursor оставлен как поле «верхняя граница», но семантика теперь
«покрыто окно [last_synced_from .. last_cursor]» с timestamp last_synced_at.

Это даёт UI:
- freshness ("синкали 5 минут назад")
- видимость окна ("покрыто X→Y")
- честный resume для мутирующих данных (статус заказа, проводка комиссии)
  через rolling-overlap: следующий run сдвигает last_synced_from на (today - N)
  если cursor дальше, чтобы перепроверить последние N дней.

Revision ID: 0018_sync_state_window
Revises: 0017_sync_state
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_sync_state_window"
down_revision = "0017_sync_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sync_state",
        sa.Column("last_synced_from", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sync_state", "last_synced_from")
