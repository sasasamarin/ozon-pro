"""
Команда и роли (field-level права).

- CompanyMember        — связка company ↔ user с конкретной ролью
- TeamInvitation       — pending-приглашения по email
- MemberAccountAccess  — гранулярный доступ к конкретному ozon_account
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class MemberRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    ACCOUNTANT = "accountant"
    VIEWER = "viewer"


class MemberStatus(str, Enum):
    INVITED = "invited"
    ACTIVE = "active"
    REVOKED = "revoked"


class InvitationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class CompanyMember(BaseModel):
    __tablename__ = "company_members"
    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_company_members_company_user"),
        Index("ix_company_members_user", "user_id"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=MemberStatus.ACTIVE.value, nullable=False
    )

    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TeamInvitation(BaseModel):
    __tablename__ = "team_invitations"
    __table_args__ = (
        UniqueConstraint("token", name="uq_team_invitations_token"),
        Index("ix_team_invitations_company_email", "company_id", "email"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    token: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=InvitationStatus.PENDING.value, nullable=False
    )


class MemberAccountAccess(BaseModel):
    """Гранулярный доступ члена команды к конкретному ozon_account."""

    __tablename__ = "member_account_access"
    __table_args__ = (
        UniqueConstraint(
            "company_member_id", "ozon_account_id", name="uq_member_account_access_pair"
        ),
    )

    company_member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company_members.id", ondelete="CASCADE"),
        nullable=False,
    )
    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )

    can_view: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    can_edit: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
