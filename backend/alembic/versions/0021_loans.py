"""loans + loan_payments: ручной учёт настоящих займов (Ozon.Invest, банк).

Тело займа в P&L не попадает — только interest_part + fee_part. Тело
видно только в ДДС. Цель — корректная прибыль при наличии займа от банка.

Revision ID: 0021_loans
Revises: 0020_storage_split
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_loans"
down_revision = "0020_storage_split"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "loans",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cabinet_id", postgresql.UUID(as_uuid=True), nullable=True,
                  comment="Опционально: к какому кабинету привязан займ. NULL = общий."),
        sa.Column("lender", sa.Text(), nullable=True, comment="Банк/партнёр"),
        sa.Column("principal", sa.Numeric(14, 2), nullable=False, comment="Тело займа"),
        sa.Column("rate_pct", sa.Numeric(6, 3), nullable=True, comment="Ставка годовых, %"),
        sa.Column("issued_at", sa.Date(), nullable=False),
        sa.Column("term_months", sa.Integer(), nullable=True),
        sa.Column("schedule_type", sa.Text(), nullable=False, server_default="annuity",
                  comment="annuity | differentiated | manual"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active",
                  comment="active | closed"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cabinet_id"], ["ozon_accounts.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_loans_company", "loans", ["company_id"])
    op.create_index("ix_loans_status_issued", "loans", ["status", "issued_at"])

    op.create_table(
        "loan_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("loan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False, comment="Номер платежа в графике"),
        sa.Column("pay_date", sa.Date(), nullable=False),
        sa.Column("principal_part", sa.Numeric(14, 2), nullable=False, server_default="0",
                  comment="Часть тела — только ДДС, в P&L НЕ попадает"),
        sa.Column("interest_part", sa.Numeric(14, 2), nullable=False, server_default="0",
                  comment="Процент — расход в P&L"),
        sa.Column("fee_part", sa.Numeric(14, 2), nullable=False, server_default="0",
                  comment="Комиссия за выдачу/обслуживание — расход в P&L"),
        sa.Column("is_paid", sa.Boolean(), nullable=False, server_default=sa.text("false"),
                  comment="Платёж факт. внесён. false = плановая строка графика"),
        sa.Column("paid_at", sa.Date(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default="schedule",
                  comment="schedule | manual | ozon_api"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("loan_id", "seq", name="uq_loan_payments_loan_seq"),
    )
    op.create_index("ix_loan_payments_company_date", "loan_payments",
                    ["company_id", "pay_date"])
    op.create_index("ix_loan_payments_loan_date", "loan_payments",
                    ["loan_id", "pay_date"])


def downgrade() -> None:
    op.drop_index("ix_loan_payments_loan_date", table_name="loan_payments")
    op.drop_index("ix_loan_payments_company_date", table_name="loan_payments")
    op.drop_table("loan_payments")
    op.drop_index("ix_loans_status_issued", table_name="loans")
    op.drop_index("ix_loans_company", table_name="loans")
    op.drop_table("loans")
