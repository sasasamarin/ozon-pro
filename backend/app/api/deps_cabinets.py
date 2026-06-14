"""
Cabinet-isolation dependencies.

Источник правды: `CompanyMember.role` + `MemberAccountAccess`.
Используется ВСЕМИ эндпоинтами, отдающими данные кабинетов.

Правила:
  • OWNER / ADMIN          — видят все кабинеты компании
  • Manager / Accountant /
    Viewer + нет MAA-строк — видят все кабинеты компании (legacy default)
  • Manager / Accountant /
    Viewer + есть MAA      — видят ТОЛЬКО кабинеты из MAA
  • CompanyMember нет      — legacy owner, видит всё
"""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import OzonAccount, User
from app.services.cabinet_access import intersect_cabinets
from app.models.team import (
    CompanyMember,
    MemberAccountAccess,
    MemberRole,
    MemberStatus,
)


async def get_accessible_cabinet_ids(
    db: AsyncSession, user: User,
) -> list[uuid.UUID] | None:
    """Список accessible cabinet_id. None = доступ ко всем кабинетам компании."""
    cm = (await db.execute(
        select(CompanyMember).where(
            CompanyMember.user_id == user.id,
            CompanyMember.company_id == user.company_id,
            CompanyMember.status == MemberStatus.ACTIVE.value,
        )
    )).scalar_one_or_none()

    if not cm:
        return None  # legacy owner

    if cm.role in (MemberRole.OWNER.value, MemberRole.ADMIN.value):
        return None

    rows = (await db.execute(
        select(MemberAccountAccess.ozon_account_id).where(
            MemberAccountAccess.company_member_id == cm.id,
        )
    )).all()
    if not rows:
        return None  # legacy default — без ограничений

    return [r[0] for r in rows]


async def get_visible_cabinet_ids(
    db: AsyncSession, user: User,
) -> list[uuid.UUID]:
    """Конкретный список UUID кабинетов, которые юзер видит.

    В отличие от `get_accessible_cabinet_ids` ВСЕГДА возвращает массив (не None) —
    подставляется напрямую в `WHERE ozon_account_id IN (...)`.
    """
    accessible = await get_accessible_cabinet_ids(db, user)
    if accessible is None:
        rows = (await db.execute(
            select(OzonAccount.id).where(
                OzonAccount.company_id == user.company_id,
                OzonAccount.deleted_at.is_(None),
            )
        )).all()
        return [r[0] for r in rows]

    # Дополнительно отсекаем удалённые / чужие — на случай stale MAA-записей
    rows = (await db.execute(
        select(OzonAccount.id).where(
            OzonAccount.company_id == user.company_id,
            OzonAccount.deleted_at.is_(None),
            OzonAccount.id.in_(accessible),
        )
    )).all()
    return [r[0] for r in rows]


async def filter_requested_cabinet_ids(
    db: AsyncSession,
    user: User,
    requested: list[uuid.UUID] | None,
) -> list[uuid.UUID]:
    """Пересечь запрошенный список с доступным. None = все доступные."""
    visible = await get_visible_cabinet_ids(db, user)
    return intersect_cabinets(requested, visible)


async def verify_cabinet_access(
    db: AsyncSession, user: User, cabinet_id: uuid.UUID | str,
) -> uuid.UUID:
    """Кинуть 403, если у юзера нет доступа к кабинету. Вернуть UUID."""
    if isinstance(cabinet_id, str):
        try:
            cabinet_id = uuid.UUID(cabinet_id)
        except ValueError:
            raise HTTPException(400, "Невалидный cabinet_id")
    visible = await get_visible_cabinet_ids(db, user)
    if cabinet_id not in visible:
        raise HTTPException(403, "Нет доступа к этому кабинету")
    return cabinet_id


# === FastAPI Depends-хелперы ===

async def visible_cabinet_ids_dep(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[uuid.UUID]:
    """Удобная инжекция: `cab_ids: list[UUID] = Depends(visible_cabinet_ids_dep)`."""
    return await get_visible_cabinet_ids(db, current_user)
