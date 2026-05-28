"""Add premium_tier, Performance API token cache, and new tables for ads + marketplace.

Single delta migration on top of the implicit baseline (DB was created via
Base.metadata.create_all). On the VPS we run `alembic stamp head` once to mark
the existing schema as up-to-date with the empty baseline, then `alembic upgrade
head` applies THIS migration.

Changes:
- ozon_accounts:
  * rename perf_secret_encrypted -> perf_client_secret_encrypted
  * add perf_access_token_encrypted, perf_token_expires_at (token cache for PA OAuth)
  * add premium_tier (free/premium/premium_plus/premium_pro, default 'free')
- new tables: returns, realization_lines, reviews, questions, ad_campaigns
- new hypertable: ad_statistics (TimescaleDB)

Revision ID: 0001_premium_perf_ad
Revises:
Create Date: 2026-05-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_premium_perf_ad"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- ozon_accounts: rename + new columns ----------
    op.alter_column(
        "ozon_accounts",
        "perf_secret_encrypted",
        new_column_name="perf_client_secret_encrypted",
    )
    op.add_column(
        "ozon_accounts",
        sa.Column("perf_access_token_encrypted", sa.Text(), nullable=True),
    )
    op.add_column(
        "ozon_accounts",
        sa.Column(
            "perf_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "ozon_accounts",
        sa.Column(
            "premium_tier",
            sa.String(length=20),
            nullable=False,
            server_default="free",
        ),
    )

    # ---------- returns ----------
    op.create_table(
        "returns",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "ozon_account_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("ozon_return_id", sa.BigInteger(), nullable=False),
        sa.Column("posting_number", sa.String(length=100), nullable=True),
        sa.Column("ozon_sku", sa.BigInteger(), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("return_type", sa.String(length=50), nullable=True),
        sa.Column("return_reason", sa.Text(), nullable=True),
        sa.Column("return_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("return_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moved_to_warehouse_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "raw_data",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'{}'::json"),
        ),
        sa.ForeignKeyConstraint(
            ["ozon_account_id"], ["ozon_accounts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ozon_account_id", "ozon_return_id", name="uq_returns_account_return"
        ),
    )
    op.create_index(
        "ix_returns_ozon_account_id", "returns", ["ozon_account_id"], unique=False
    )
    op.create_index(
        "ix_returns_product_id", "returns", ["product_id"], unique=False
    )
    op.create_index(
        "ix_returns_account_date",
        "returns",
        ["ozon_account_id", "return_date"],
        unique=False,
    )

    # ---------- realization_lines ----------
    op.create_table(
        "realization_lines",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "ozon_account_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("ozon_sku", sa.BigInteger(), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("offer_id", sa.String(length=255), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("qty_sold", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("qty_returned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revenue", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("commission_amount", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("delivery_amount", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("refund_amount", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column(
            "raw_data",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'{}'::json"),
        ),
        sa.ForeignKeyConstraint(
            ["ozon_account_id"], ["ozon_accounts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ozon_account_id",
            "period_from",
            "period_to",
            "ozon_sku",
            name="uq_realization_account_period_sku",
        ),
    )
    op.create_index(
        "ix_realization_lines_ozon_account_id",
        "realization_lines",
        ["ozon_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_realization_lines_product_id",
        "realization_lines",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        "ix_realization_account_period",
        "realization_lines",
        ["ozon_account_id", "period_from", "period_to"],
        unique=False,
    )

    # ---------- reviews ----------
    op.create_table(
        "reviews",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "ozon_account_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("ozon_review_id", sa.String(length=64), nullable=False),
        sa.Column("ozon_sku", sa.BigInteger(), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("author_name", sa.String(length=255), nullable=True),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column("review_text", sa.Text(), nullable=True),
        sa.Column("pluses", sa.Text(), nullable=True),
        sa.Column("minuses", sa.Text(), nullable=True),
        sa.Column("review_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=True),
        sa.Column("has_response", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("has_photos", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("has_videos", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "raw_data",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'{}'::json"),
        ),
        sa.ForeignKeyConstraint(
            ["ozon_account_id"], ["ozon_accounts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ozon_account_id", "ozon_review_id", name="uq_reviews_account_review"
        ),
    )
    op.create_index(
        "ix_reviews_ozon_account_id", "reviews", ["ozon_account_id"], unique=False
    )
    op.create_index("ix_reviews_product_id", "reviews", ["product_id"], unique=False)
    op.create_index(
        "ix_reviews_account_date",
        "reviews",
        ["ozon_account_id", "review_date"],
        unique=False,
    )
    op.create_index("ix_reviews_sku", "reviews", ["ozon_sku"], unique=False)

    # ---------- questions ----------
    op.create_table(
        "questions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "ozon_account_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("ozon_question_id", sa.String(length=64), nullable=False),
        sa.Column("ozon_sku", sa.BigInteger(), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("author_name", sa.String(length=255), nullable=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("question_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("answer_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=True),
        sa.Column(
            "raw_data",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'{}'::json"),
        ),
        sa.ForeignKeyConstraint(
            ["ozon_account_id"], ["ozon_accounts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ozon_account_id", "ozon_question_id", name="uq_questions_account_question"
        ),
    )
    op.create_index(
        "ix_questions_ozon_account_id", "questions", ["ozon_account_id"], unique=False
    )
    op.create_index(
        "ix_questions_product_id", "questions", ["product_id"], unique=False
    )
    op.create_index(
        "ix_questions_account_date",
        "questions",
        ["ozon_account_id", "question_date"],
        unique=False,
    )
    op.create_index("ix_questions_sku", "questions", ["ozon_sku"], unique=False)

    # ---------- ad_campaigns ----------
    op.create_table(
        "ad_campaigns",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "ozon_account_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("ozon_campaign_id", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "campaign_type",
            sa.String(length=30),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "state",
            sa.String(length=20),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("from_date", sa.Date(), nullable=True),
        sa.Column("to_date", sa.Date(), nullable=True),
        sa.Column("daily_budget", sa.Numeric(15, 2), nullable=True),
        sa.Column("weekly_budget", sa.Numeric(15, 2), nullable=True),
        sa.Column("budget", sa.Numeric(15, 2), nullable=True),
        sa.Column(
            "raw_data",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'{}'::json"),
        ),
        sa.ForeignKeyConstraint(
            ["ozon_account_id"], ["ozon_accounts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ozon_account_id",
            "ozon_campaign_id",
            name="uq_ad_campaigns_account_campaign",
        ),
    )
    op.create_index(
        "ix_ad_campaigns_ozon_account_id",
        "ad_campaigns",
        ["ozon_account_id"],
        unique=False,
    )
    op.create_index("ix_ad_campaigns_state", "ad_campaigns", ["state"], unique=False)

    # ---------- ad_statistics (TimescaleDB hypertable) ----------
    op.create_table(
        "ad_statistics",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("ozon_campaign_id", sa.String(length=50), nullable=False),
        sa.Column(
            "ozon_account_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("views", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revenue", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("money_spent", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("ctr", sa.Numeric(7, 4), nullable=True),
        sa.Column("drr", sa.Numeric(7, 4), nullable=True),
        sa.Column(
            "raw_data",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["ozon_account_id"], ["ozon_accounts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("date", "ozon_campaign_id"),
    )
    op.create_index(
        "ix_ad_statistics_account_date",
        "ad_statistics",
        ["ozon_account_id", "date"],
        unique=False,
    )
    op.create_index(
        "ix_ad_statistics_campaign_date",
        "ad_statistics",
        ["ozon_campaign_id", "date"],
        unique=False,
    )

    # Convert ad_statistics into a TimescaleDB hypertable.
    # `if_not_exists` keeps the op idempotent; `migrate_data` is unnecessary on an empty table.
    op.execute(
        "SELECT create_hypertable("
        "'ad_statistics', 'date', "
        "chunk_time_interval => INTERVAL '30 days', "
        "if_not_exists => TRUE"
        ")"
    )


def downgrade() -> None:
    # Reverse in dependency order (drop FK-referencing tables first).
    op.drop_index("ix_ad_statistics_campaign_date", table_name="ad_statistics")
    op.drop_index("ix_ad_statistics_account_date", table_name="ad_statistics")
    op.drop_table("ad_statistics")

    op.drop_index("ix_ad_campaigns_state", table_name="ad_campaigns")
    op.drop_index("ix_ad_campaigns_ozon_account_id", table_name="ad_campaigns")
    op.drop_table("ad_campaigns")

    op.drop_index("ix_questions_sku", table_name="questions")
    op.drop_index("ix_questions_account_date", table_name="questions")
    op.drop_index("ix_questions_product_id", table_name="questions")
    op.drop_index("ix_questions_ozon_account_id", table_name="questions")
    op.drop_table("questions")

    op.drop_index("ix_reviews_sku", table_name="reviews")
    op.drop_index("ix_reviews_account_date", table_name="reviews")
    op.drop_index("ix_reviews_product_id", table_name="reviews")
    op.drop_index("ix_reviews_ozon_account_id", table_name="reviews")
    op.drop_table("reviews")

    op.drop_index("ix_realization_account_period", table_name="realization_lines")
    op.drop_index("ix_realization_lines_product_id", table_name="realization_lines")
    op.drop_index("ix_realization_lines_ozon_account_id", table_name="realization_lines")
    op.drop_table("realization_lines")

    op.drop_index("ix_returns_account_date", table_name="returns")
    op.drop_index("ix_returns_product_id", table_name="returns")
    op.drop_index("ix_returns_ozon_account_id", table_name="returns")
    op.drop_table("returns")

    op.drop_column("ozon_accounts", "premium_tier")
    op.drop_column("ozon_accounts", "perf_token_expires_at")
    op.drop_column("ozon_accounts", "perf_access_token_encrypted")
    op.alter_column(
        "ozon_accounts",
        "perf_client_secret_encrypted",
        new_column_name="perf_secret_encrypted",
    )
