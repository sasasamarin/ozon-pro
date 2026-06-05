"""
RBAC для раздела «План продаж»: фильтрация по доступным кабинетам.

Логика:
  • OWNER / ADMIN — видят все кабинеты компании
  • Прочие роли — видят кабинеты, на которые есть MemberAccountAccess.
    Если у CompanyMember нет ни одной MemberAccountAccess записи —
    подразумевается «доступ ко всем» (legacy совместимость).
  • Если нет CompanyMember-строки (юзер сам создал компанию) — OWNER.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OzonAccount, User
from app.models.team import (
    CompanyMember, MemberAccountAccess, MemberRole, MemberStatus,
)


async def get_accessible_cabinet_ids(
    db: AsyncSession, user: User,
) -> list[uuid.UUID] | None:
    """Возвращает список accessible cabinet_id для юзера.

    Возвращает `None` если юзер видит ВСЕ кабинеты компании (OWNER/ADMIN
    или у CompanyMember нет MemberAccountAccess правил).

    Если возвращён список — фильтровать SQL по `OzonAccount.id IN list`.
    """
    cm = (await db.execute(
        select(CompanyMember).where(
            CompanyMember.user_id == user.id,
            CompanyMember.company_id == user.company_id,
            CompanyMember.status == MemberStatus.ACTIVE.value,
        )
    )).scalar_one_or_none()

    if not cm:
        # Legacy: юзер сам создал компанию → OWNER, видит всё
        return None

    role = cm.role
    if role in (MemberRole.OWNER.value, MemberRole.ADMIN.value):
        return None  # видит всё

    # Manager/Accountant/Viewer — смотрим MemberAccountAccess
    rows = (await db.execute(
        select(MemberAccountAccess.ozon_account_id).where(
            MemberAccountAccess.company_member_id == cm.id,
        )
    )).all()
    if not rows:
        # Нет per-cabinet ограничений → видит все кабинеты компании (default)
        return None

    return [r[0] for r in rows]


async def filter_cabinet_ids(
    db: AsyncSession, user: User, requested: list[uuid.UUID] | None,
) -> list[uuid.UUID] | None:
    """Пересечение запрошенных кабинетов и accessible.

    Если accessible=None (все) → возвращает requested как есть.
    Если requested=None (все запрошены) → возвращает accessible.
    Иначе → пересечение.
    """
    accessible = await get_accessible_cabinet_ids(db, user)
    if accessible is None:
        return requested
    if requested is None or len(requested) == 0:
        return accessible
    accessible_set = set(accessible)
    return [c for c in requested if c in accessible_set]
