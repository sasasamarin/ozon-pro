"""MVP «Поставки»: ручной ввод поставок (машина/вагон со SKU + затраты + документы).

Принципы:
- Авто-распределения затрат НЕТ. final_unit_cost и total_cost = source='manual'.
- product_id кладём сразу (потом эта поставка будет питать себестоимость).
- Σ затрат показываем справочно, в себестоимость НЕ пишем.

Фаза 2 заранее: expected_date, shipment_deadline, status — поля NULL/default,
чтобы timeline-календарь и прогноз закупок сели без новой миграции.

Revision ID: 0023_supplies
Revises: 0022_customer_price_source
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0023_supplies"
down_revision = "0022_customer_price_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # === supplies ===
    op.create_table(
        "supplies",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cabinet_id", postgresql.UUID(as_uuid=True), nullable=True,
                  comment="Опциональная привязка к кабинету Ozon"),
        sa.Column("name", sa.Text(), nullable=False, comment="Метка/название поставки"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual",
                  comment="manual | imported (фаза 2)"),
        sa.Column("total_cost", sa.Numeric(14, 2), nullable=True,
                  comment="Итоговая стоимость поставки (если юзер заполнит вручную). "
                          "В себестоимость НЕ пишется автоматически."),
        # Даты MVP (все nullable, ручной ввод)
        sa.Column("payment_date", sa.Date(), nullable=True),
        sa.Column("dispatch_date", sa.Date(), nullable=True),
        sa.Column("dispatch_from", sa.String(255), nullable=True,
                  comment="Откуда отправлено (станция / склад поставщика, свободный текст)"),
        sa.Column("actual_departure_date", sa.Date(), nullable=True),
        sa.Column("supply_date", sa.Date(), nullable=True,
                  comment="Дата прихода/получения"),
        # Фаза 2 — поля под timeline-календарь, дедлайны, статусы
        sa.Column("expected_date", sa.Date(), nullable=True,
                  comment="ФАЗА 2: ожидаемая дата прибытия для timeline"),
        sa.Column("shipment_deadline", sa.Date(), nullable=True,
                  comment="ФАЗА 2: дедлайн отгрузки на Ozon"),
        sa.Column("status", sa.String(20), nullable=False, server_default="arrived",
                  comment="ФАЗА 2: ordered | in_transit | arrived"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cabinet_id"], ["ozon_accounts.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_supplies_company_date", "supplies",
                    ["company_id", "supply_date"])
    op.create_index("ix_supplies_status_expected", "supplies",
                    ["status", "expected_date"])

    # === supply_items ===
    op.create_table(
        "supply_items",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("supply_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True,
                  comment="Сматчено с products.id. NULL допустим если SKU вне каталога."),
        sa.Column("offer_id", sa.String(255), nullable=True),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("final_unit_cost", sa.Numeric(14, 2), nullable=True,
                  comment="Финальная себестоимость за единицу (юзер вписывает вручную, "
                          "учитывая распределение общих затрат)"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["supply_id"], ["supplies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_supply_items_supply", "supply_items", ["supply_id"])
    op.create_index("ix_supply_items_product", "supply_items", ["product_id"])

    # === supply_costs ===
    op.create_table(
        "supply_costs",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("supply_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supply_item_id", postgresql.UUID(as_uuid=True), nullable=True,
                  comment="Если scope='item' — на какой SKU"),
        sa.Column("name", sa.Text(), nullable=False,
                  comment="Название затраты: «доставка», «растаможка», «сертификат»…"),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("scope", sa.String(10), nullable=False,
                  comment="supply (на всю поставку) | item (на конкретный товар)"),
        sa.Column("note", sa.Text(), nullable=True,
                  comment="Свободная заметка по затрате"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["supply_id"], ["supplies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supply_item_id"], ["supply_items.id"], ondelete="SET NULL"),
        sa.CheckConstraint("scope IN ('supply','item')", name="ck_supply_costs_scope"),
    )
    op.create_index("ix_supply_costs_supply", "supply_costs", ["supply_id"])

    # === supply_documents ===
    op.create_table(
        "supply_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("supply_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supply_item_id", postgresql.UUID(as_uuid=True), nullable=True,
                  comment="Если документ привязан к конкретной позиции"),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("mime", sa.String(100), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["supply_id"], ["supplies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supply_item_id"], ["supply_items.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_supply_documents_supply", "supply_documents", ["supply_id"])


def downgrade() -> None:
    op.drop_table("supply_documents")
    op.drop_table("supply_costs")
    op.drop_table("supply_items")
    op.drop_table("supplies")
