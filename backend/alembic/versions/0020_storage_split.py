"""storage split: + storage_from_xlsx, + placement_storage_daily.

Раздельные источники хранения:
- monthly_unit_economy.storage_from_xlsx — ручной XLSX «Общие расходы»
  (календарный месяц, точно, приоритет).
- placement_storage_daily — сырые daily записи из Report API
  seller_placement_by_products (PK по дню → перекрывающиеся отчёты не дают
  двойного счёта).

monthly_unit_economy.storage НЕ ДРОПАЕМ — оставляем для отката. P&L на
него больше не смотрит после ШАГА продукта.

Revision ID: 0020_storage_split
Revises: 0019_monthly_unit_economy
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_storage_split"
down_revision = "0019_monthly_unit_economy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Новая колонка для точного XLSX-хранения
    op.add_column(
        "monthly_unit_economy",
        sa.Column("storage_from_xlsx", sa.Numeric(14, 4), nullable=True,
                  comment="Точное хранение из ручного XLSX «Общие расходы». Приоритет над daily API."),
    )

    # 2. Backfill из существующего storage только для ручных XLSX
    op.execute("""
        UPDATE monthly_unit_economy
        SET storage_from_xlsx = storage
        WHERE source_file IS NOT NULL
          AND source_file NOT LIKE 'REPORT_%'
          AND storage IS NOT NULL
    """)

    # 3. Новая таблица сырого хранения per day per warehouse
    op.create_table(
        "placement_storage_daily",
        sa.Column("cabinet_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.BigInteger(), nullable=False),
        sa.Column("warehouse", sa.Text(), nullable=False, server_default=""),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("storage_cost", sa.Numeric(14, 4), nullable=False),
        sa.Column("source_report", sa.Text(), nullable=True,
                  comment="Code отчёта из /v1/report/list (REPORT_seller_placement_by_products_...)"),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("cabinet_id", "sku", "warehouse", "day",
                                name="pk_placement_storage_daily"),
        sa.ForeignKeyConstraint(
            ["cabinet_id"], ["ozon_accounts.id"],
            name="fk_placement_storage_daily_cabinet", ondelete="CASCADE",
        ),
    )
    # Для агрегатов SUM(storage_cost) WHERE day IN month
    op.create_index(
        "ix_placement_storage_daily_sku_day",
        "placement_storage_daily",
        ["cabinet_id", "sku", "day"],
    )


def downgrade() -> None:
    op.drop_index("ix_placement_storage_daily_sku_day", table_name="placement_storage_daily")
    op.drop_table("placement_storage_daily")
    op.drop_column("monthly_unit_economy", "storage_from_xlsx")
