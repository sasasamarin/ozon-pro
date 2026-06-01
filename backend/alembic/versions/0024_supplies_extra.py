"""supplies extra: tag, transport_type, route, item.name, cost.currency.

- supplies.tag: свободный тег для группировки
- supplies.transport_type: rzd|auto|auto_consolidated|cargo|sea
- supplies.route: маршрут (свободный текст)
- supply_items.name: override-название для товаров не из каталога
- supply_costs.currency: USD|RUB|NULL (валюта затраты)

Имя оставлено коротким — alembic_version.version_num = VARCHAR(32),
длинные имена не помещаются.

Revision ID: 0024_supplies_extra
Revises: 0023_supplies
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_supplies_extra"
down_revision = "0023_supplies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("supplies", sa.Column("tag", sa.String(100), nullable=True))
    op.add_column("supplies", sa.Column("transport_type", sa.String(30), nullable=True,
                                        comment="rzd | auto | auto_consolidated | cargo | sea"))
    op.add_column("supplies", sa.Column("route", sa.Text(), nullable=True))
    op.add_column("supply_items", sa.Column("name", sa.Text(), nullable=True,
                                            comment="Override-название (если SKU не из каталога)"))
    op.add_column("supply_costs", sa.Column("currency", sa.String(3), nullable=True,
                                            comment="USD | RUB | NULL"))


def downgrade() -> None:
    op.drop_column("supply_costs", "currency")
    op.drop_column("supply_items", "name")
    op.drop_column("supplies", "route")
    op.drop_column("supplies", "transport_type")
    op.drop_column("supplies", "tag")
