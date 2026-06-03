"""AI Phase 1 (FLOWOI_AI_TZ §5): ai_chat_sessions + ai_chat_messages.

Новые таблицы для AI-чата с function calling, cabinet_scope и
attachments (контекст графика, не картинка). Старые ai_chats/ai_messages
остаются — другой семантический слой (legacy Anthropic-block).

Revision ID: 0029_ai_chat_sessions
Revises: 0028_premium_endpoints
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0029_ai_chat_sessions"
down_revision = "0028_premium_endpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("cabinet_scope", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ai_chat_sessions_user", "ai_chat_sessions", ["user_id"])

    op.create_table(
        "ai_chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("tool_calls", postgresql.JSONB, nullable=True),
        sa.Column("attachments", postgresql.JSONB, nullable=True),
        sa.Column("model_used", sa.String(80), nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["ai_chat_sessions.id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_ai_chat_messages_session_created", "ai_chat_messages",
                    ["session_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_chat_messages_session_created", table_name="ai_chat_messages")
    op.drop_table("ai_chat_messages")
    op.drop_index("ix_ai_chat_sessions_user", table_name="ai_chat_sessions")
    op.drop_table("ai_chat_sessions")
