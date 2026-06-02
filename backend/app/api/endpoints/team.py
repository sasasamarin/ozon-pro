"""
/team — управление командой: invite + accept + members.
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
from app.core.config import settings
from app.core.logging import log
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.db.session import get_db
from app.models import Company, User
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

    # Email с правильной ссылкой на /accept-invite
    base_url = (getattr(settings, "PUBLIC_URL", None) or "https://flowoi.ru").rstrip("/")
    accept_link = f"{base_url}/accept-invite?token={inv.token}"
    company = (await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )).scalar_one_or_none()
    company_name = company.name if company else "Flowoi"
    try:
        from app.services.email import send_email
        inviter_name = current_user.full_name or current_user.email
        text = (
            f"Здравствуйте!\n\n"
            f"Вас пригласил {inviter_name} в команду «{company_name}» "
            f"на роль «{inv.role}» в Flowoi (flowoi.ru).\n\n"
            f"Чтобы принять приглашение и получить доступ к данным кабинетов "
            f"Ozon — пройдите по ссылке:\n\n{accept_link}\n\n"
            f"Ссылка действует 7 дней.\n\n"
            f"Если вы не ожидали этого письма — просто проигнорируйте.\n"
        )
        html = (
            f"<p>Здравствуйте!</p>"
            f"<p><b>{inviter_name}</b> приглашает вас в команду "
            f"«<b>{company_name}</b>» на роль «{inv.role}» в Flowoi (flowoi.ru).</p>"
            f"<p style='margin:24px 0'>"
            f"<a href='{accept_link}' style='background:#4f46e5;color:white;"
            f"padding:12px 20px;border-radius:8px;text-decoration:none;"
            f"font-weight:600'>Принять приглашение</a></p>"
            f"<p style='color:#666;font-size:13px'>Или скопируйте ссылку:<br>"
            f"<a href='{accept_link}'>{accept_link}</a></p>"
            f"<p style='color:#999;font-size:12px'>Ссылка действует 7 дней. "
            f"Если вы не ожидали этого письма — просто проигнорируйте.</p>"
        )
        await send_email(to=inv.email, subject=f"Приглашение в {company_name} (Flowoi)",
                         html=html, text=text)
    except Exception:
        log.exception("invite_email_failed", invitation_id=str(inv.id))

    return InvitationRow(
        id=str(inv.id), email=inv.email, role=inv.role, status=inv.status,
        expires_at=inv.expires_at.isoformat(),
        invite_link=accept_link,
    )


# ============================================================
# Accept invitation — публичный (без auth)
# ============================================================


class InvitePreview(BaseModel):
    email: str
    role: str
    company_name: str
    expires_at: str
    already_user: bool       # True если этот email уже зарегистрирован


class AcceptInviteRequest(BaseModel):
    token: str
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class AcceptInviteResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


async def _get_invitation_by_token(db: AsyncSession, token: str) -> TeamInvitation:
    inv = (await db.execute(
        select(TeamInvitation).where(TeamInvitation.token == token)
    )).scalar_one_or_none()
    if not inv:
        raise HTTPException(404, "Приглашение не найдено")
    if inv.status != InvitationStatus.PENDING.value:
        raise HTTPException(400, f"Приглашение уже {inv.status}")
    if inv.expires_at < datetime.now(UTC):
        raise HTTPException(400, "Срок приглашения истёк")
    return inv


@router.get("/invitations/preview/{token}", response_model=InvitePreview)
async def preview_invitation(
    token: str, db: AsyncSession = Depends(get_db),
) -> InvitePreview:
    """Публичный endpoint — нужен для UI страницы принятия (нет auth)."""
    inv = await _get_invitation_by_token(db, token)
    company = (await db.execute(
        select(Company).where(Company.id == inv.company_id)
    )).scalar_one_or_none()
    user_exists = (await db.execute(
        select(User.id).where(User.email == inv.email)
    )).scalar_one_or_none()
    return InvitePreview(
        email=inv.email, role=inv.role,
        company_name=company.name if company else "—",
        expires_at=inv.expires_at.isoformat(),
        already_user=bool(user_exists),
    )


@router.post("/invitations/accept", response_model=AcceptInviteResponse)
async def accept_invitation(
    payload: AcceptInviteRequest,
    db: AsyncSession = Depends(get_db),
) -> AcceptInviteResponse:
    """
    Принять приглашение: создать User (если ещё нет) + CompanyMember +
    пометить приглашение accepted. Auto-login через JWT.
    """
    inv = await _get_invitation_by_token(db, payload.token)

    # User: либо существующий с этим email (просто привязываем к company),
    # либо новый.
    user = (await db.execute(
        select(User).where(User.email == inv.email)
    )).scalar_one_or_none()
    if not user:
        user = User(
            email=inv.email,
            full_name=payload.full_name,
            hashed_password=hash_password(payload.password),
            company_id=inv.company_id,
            is_active=True,
        )
        db.add(user)
        await db.flush()
    else:
        # Существующий юзер: переключаем основную компанию на ту, в которую
        # пригласили. Все endpoints читают current_user.company_id → юзер
        # увидит кабинет приглашающего. Пароль не трогаем.
        user.company_id = inv.company_id

    # CompanyMember — проверяем чтобы не дублировать
    existing_member = (await db.execute(
        select(CompanyMember).where(
            CompanyMember.company_id == inv.company_id,
            CompanyMember.user_id == user.id,
        )
    )).scalar_one_or_none()
    if not existing_member:
        db.add(CompanyMember(
            company_id=inv.company_id,
            user_id=user.id,
            role=inv.role,
            status=MemberStatus.ACTIVE.value,
            accepted_at=datetime.now(UTC),
        ))

    inv.status = InvitationStatus.ACCEPTED.value
    await db.commit()

    return AcceptInviteResponse(
        access_token=create_access_token(subject=str(user.id)),
        refresh_token=create_refresh_token(subject=str(user.id)),
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
