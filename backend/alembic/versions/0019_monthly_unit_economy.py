"""monthly_unit_economy: точные per-product финрасходы из XLSX «Экономика магазина».

Ozon публичным Seller API per-product storage / реклама / эквайринг НЕ отдаёт.
Юзер раз в месяц выгружает XLSX «Юнит-экономика → Общие расходы» и грузит
через UI Flowoi. Точное зеркало Ozon без оценок.

Revision ID: 0019_monthly_unit_economy
Revises: 0018_sync_state_window
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_monthly_unit_economy"
down_revision = "0018_sync_state_window"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monthly_unit_economy",
        # PK: (cabinet, sku, month)
        sa.Column("cabinet_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.BigInteger(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False, comment="первый день месяца (2026-05-01)"),
        # Период из строки 1 файла (Ozon точный диапазон)
        sa.Column("period_from", sa.Date(), nullable=True),
        sa.Column("period_to", sa.Date(), nullable=True),
        # Идентификация товара
        sa.Column("offer_id", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("scheme", sa.Text(), nullable=True, comment="FBO/FBS"),
        sa.Column("current_price", sa.Numeric(14, 4), nullable=True),
        # Количества
        sa.Column("ordered_qty", sa.Integer(), nullable=True),
        sa.Column("delivered_qty", sa.Integer(), nullable=True),
        sa.Column("returned_qty", sa.Integer(), nullable=True),
        # Доходы продавца
        sa.Column("revenue", sa.Numeric(14, 4), nullable=True),
        sa.Column("spp_points", sa.Numeric(14, 4), nullable=True, comment="Баллы за скидки"),
        sa.Column("partner_programs", sa.Numeric(14, 4), nullable=True),
        # Расходы Ozon (отрицательные в файле)
        sa.Column("ozon_commission", sa.Numeric(14, 4), nullable=True),
        sa.Column("acquiring", sa.Numeric(14, 4), nullable=True),
        sa.Column("posting_handling", sa.Numeric(14, 4), nullable=True),
        sa.Column("logistics", sa.Numeric(14, 4), nullable=True),
        sa.Column("last_mile", sa.Numeric(14, 4), nullable=True, comment="Доставка до места выдачи"),
        sa.Column("storage", sa.Numeric(14, 4), nullable=True, comment="Стоимость размещения"),
        sa.Column("return_handling", sa.Numeric(14, 4), nullable=True),
        sa.Column("reverse_logistics", sa.Numeric(14, 4), nullable=True),
        sa.Column("disposal", sa.Numeric(14, 4), nullable=True, comment="Утилизация"),
        sa.Column("ovh_extra", sa.Numeric(14, 4), nullable=True, comment="Доп. обработка ОВХ"),
        sa.Column("operational_errors", sa.Numeric(14, 4), nullable=True),
        # Реклама по видам
        sa.Column("ad_cpc", sa.Numeric(14, 4), nullable=True, comment="Оплата за клик"),
        sa.Column("ad_cpo", sa.Numeric(14, 4), nullable=True, comment="Оплата за заказ"),
        sa.Column("ad_star", sa.Numeric(14, 4), nullable=True, comment="Звёздные товары"),
        sa.Column("ad_paid_brand", sa.Numeric(14, 4), nullable=True, comment="Платный бренд"),
        sa.Column("ad_reviews", sa.Numeric(14, 4), nullable=True, comment="Отзывы"),
        # Расчётные поля Ozon (для сверки)
        sa.Column("ozon_profit", sa.Numeric(14, 4), nullable=True, comment="Прибыль за период (расч. Ozon)"),
        sa.Column("ozon_margin_share", sa.Numeric(8, 4), nullable=True),
        sa.Column("price_index", sa.Numeric(8, 4), nullable=True),
        # Метаданные
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("source_file", sa.Text(), nullable=True, comment="имя XLSX файла"),
        sa.PrimaryKeyConstraint("cabinet_id", "sku", "month",
                                name="pk_monthly_unit_economy"),
        sa.ForeignKeyConstraint(
            ["cabinet_id"], ["ozon_accounts.id"],
            name="fk_monthly_unit_economy_cabinet", ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_monthly_unit_economy_month_cab",
        "monthly_unit_economy",
        ["month", "cabinet_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_monthly_unit_economy_month_cab", table_name="monthly_unit_economy")
    op.drop_table("monthly_unit_economy")
