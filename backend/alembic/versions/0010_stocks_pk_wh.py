"""stocks PK включает warehouse_name — иначе sync_warehouse_stocks теряет 95%+ строк.

Ozon /v2/analytics/stock_on_warehouses отдаёт разбивку по 22-30 складам РФЦ
per товар, но у нас PK (time, product_id, warehouse_type) → ON CONFLICT DO NOTHING
пропускает все строки кроме первой. В итоге в БД 19 FBO_WH строк вместо ожидаемых
сотен.

Решение:
  1) NULL warehouse_name → '<aggregate>' (для старых AGG/FBO/FBS/RFBS строк
     без склада — это значит "суммарно по типу")
  2) дедуп: для каждой группы (time, pid, wh_type, warehouse_name) оставляем
     только последний ctid (~1160 дублей в БД)
  3) NOT NULL + PK включает warehouse_name

TimescaleDB разрешает менять PK, пока он содержит time (=партиционный ключ).

Revision ID: 0010_stocks_pk_wh
Revises: 0009_ad_stats_pk
"""
from __future__ import annotations

from alembic import op


revision = "0010_stocks_pk_wh"
down_revision = "0009_ad_stats_pk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE stocks SET warehouse_name = '<aggregate>' "
        "WHERE warehouse_name IS NULL"
    )
    # Дедуп: оставляем только последний ctid в каждой группе ключей
    op.execute(
        """
        DELETE FROM stocks WHERE ctid IN (
          SELECT ctid FROM (
            SELECT ctid,
                   ROW_NUMBER() OVER (
                     PARTITION BY time, product_id, warehouse_type, warehouse_name
                     ORDER BY ctid DESC
                   ) AS rn
            FROM stocks
          ) ranked
          WHERE rn > 1
        )
        """
    )
    op.execute("ALTER TABLE stocks ALTER COLUMN warehouse_name SET NOT NULL")
    op.execute("ALTER TABLE stocks DROP CONSTRAINT IF EXISTS pk_stocks")
    op.execute(
        "ALTER TABLE stocks ADD CONSTRAINT pk_stocks "
        "PRIMARY KEY (time, product_id, warehouse_type, warehouse_name)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE stocks DROP CONSTRAINT IF EXISTS pk_stocks")
    op.execute(
        "ALTER TABLE stocks ADD CONSTRAINT pk_stocks "
        "PRIMARY KEY (time, product_id, warehouse_type)"
    )
    op.execute("ALTER TABLE stocks ALTER COLUMN warehouse_name DROP NOT NULL")
    op.execute(
        "UPDATE stocks SET warehouse_name = NULL "
        "WHERE warehouse_name = '<aggregate>'"
    )
