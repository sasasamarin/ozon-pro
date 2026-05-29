"""
/team — управление командой (read-only + базовый invite).
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.models.team import (
    CompanyMember,
    InvitationStatus,
    MemberRole,
    MemberStatus,
    TeamInvitation,
)

router = APIRouter()
UTC = timezone.utc


class MemberRow(BaseModel):
    id: str
    user_id: str
    email: str
    full_name: str | None
    role: str
    status: str
    accepted_at: str | None


class InvitationRow(BaseModel):
    id: str
    email: str
    role: str
    status: str
    expires_at: str
    invite_link: str


class InviteCreate(BaseModel):
    email: EmailStr
    role: str = MemberRole.MANAGER.value


@router.get("/members", response_model=list[MemberRow])
async def list_members(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MemberRow]:
    rows = (await db.execute(
        select(CompanyMember, User)
        .join(User, User.id == CompanyMember.user_id)
        .where(CompanyMember.company_id == current_user.company_id)
    )).all()
    out: list[MemberRow] = []
    # сам owner — добавим даже если CompanyMember нет (исторически)
    has_owner_in_members = False
    for cm, u in rows:
        if u.id == current_user.id:
            has_owner_in_members = True
        out.append(MemberRow(
            id=str(cm.id), user_id=str(u.id), email=u.email,
            full_name=u.full_name, role=cm.role, status=cm.status,
            accepted_at=cm.accepted_at.isoformat() if cm.accepted_at else None,
        ))
    if not has_owner_in_members:
        out.insert(0, MemberRow(
            id=str(current_user.id), user_id=str(current_user.id),
            email=current_user.email, full_name=current_user.full_name,
            role=MemberRole.OWNER.value, status=MemberStatus.ACTIVE.value,
            accepted_at=None,
        ))
    return out


@router.get("/invitations", response_model=list[InvitationRow])
async def list_invitations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[InvitationRow]:
    rows = (await db.execute(
        select(TeamInvitation).where(
            TeamInvitation.company_id == current_user.company_id,
            TeamInvitation.status == InvitationStatus.PENDING.value,
        )
    )).scalars().all()
    return [
        InvitationRow(
            id=str(i.id), email=i.email, role=i.role,
            status=i.status,
            expires_at=i.expires_at.isoformat(),
            invite_link=f"/register?invite={i.token}",
        )
        for i in rows
    ]


@router.post("/invitations", response_model=InvitationRow)
async def create_invitation(
    payload: InviteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvitationRow:
    valid_roles = {r.value for r in MemberRole if r != MemberRole.OWNER}
    if payload.role not in valid_roles:
        raise HTTPException(400, f"Невалидная роль: {payload.role}")

    inv = TeamInvitation(
        company_id=current_user.company_id,
        email=payload.email,
        role=payload.role,
        token=secrets.token_urlsafe(32),
        expires_at=datetime.now(UTC) + timedelta(days=7),
        created_by_user_id=current_user.id,
    )
    db.add(inv)
    await db.commit()
    await db.refresh(inv)
    return InvitationRow(
        id=str(inv.id), email=inv.email, role=inv.role, status=inv.status,
        expires_at=inv.expires_at.isoformat(),
        invite_link=f"/register?invite={inv.token}",
    )


@router.delete("/invitations/{invitation_id}")
async def revoke_invitation(
    invitation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        iid = uuid.UUID(invitation_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")
    inv = (await db.execute(
        select(TeamInvitation).where(
            TeamInvitation.id == iid,
            TeamInvitation.company_id == current_user.company_id,
        )
    )).scalar_one_or_none()
    if not inv:
        raise HTTPException(404, "Не найдено")
    inv.status = InvitationStatus.REVOKED.value
    await db.commit()
    return {"revoked": True}
