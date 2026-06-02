"""+ analytics_daily.hits_view, session_view — общие метрики «Показы Ozon UI».

Корень: hits_view_search + hits_view_pdp = ~93k, а Ozon UI «Показы» = hits_view
(общая) = ~363k. Это РАЗНЫЕ метрики в /v1/analytics/data — мы тянули только
разбитые. Добавляем общие.

Revision ID: 0027_analytics_hits_view
Revises: 0026_dashboard_layouts
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027_analytics_hits_view"
down_revision = "0026_dashboard_layouts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analytics_daily", sa.Column("hits_view", sa.Integer(), nullable=True,
        comment="Общая метрика «Показы Ozon UI» = карточка в выдаче. ≠ hits_view_search+pdp."))
    op.add_column("analytics_daily", sa.Column("session_view", sa.Integer(), nullable=True,
        comment="Общие сессии просмотров (Ozon UI «Уникальные посетители»)."))


def downgrade() -> None:
    op.drop_column("analytics_daily", "session_view")
    op.drop_column("analytics_daily", "hits_view")
