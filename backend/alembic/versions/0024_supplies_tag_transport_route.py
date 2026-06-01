"""+ supplies.tag, transport_type, route.

- tag: свободный тег для группировки (например партия, поставщик)
- transport_type: rzd|auto|auto_consolidated|cargo|sea — тип перевозки
- route: свободный текст маршрута («Шэньчжэнь → Москва, через Алматы»)

Revision ID: 0024_supplies_tag_transport_route
Revises: 0023_supplies
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_supplies_tag_transport_route"
down_revision = "0023_supplies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("supplies", sa.Column("tag", sa.String(100), nullable=True,
                                        comment="Метка/тэг для группировки"))
    op.add_column("supplies", sa.Column("transport_type", sa.String(30), nullable=True,
                                        comment="rzd | auto | auto_consolidated | cargo | sea"))
    op.add_column("supplies", sa.Column("route", sa.Text(), nullable=True,
                                        comment="Маршрут (свободный текст)"))


def downgrade() -> None:
    op.drop_column("supplies", "route")
    op.drop_column("supplies", "transport_type")
    op.drop_column("supplies", "tag")
