"""
RBAC helpers — проверка ролей для destructive endpoint-ов.

Роли в порядке убывания прав (см. MemberRole):
  OWNER       — полный доступ. Только владелец компании.
  ADMIN       — всё кроме удаления компании / смены биллинга.
  MANAGER     — операционные действия: цены, остатки, закупки.
  ACCOUNTANT  — финансы: кредиты, расходы, налоги.
  VIEWER      — только чтение.

Использование:
    @router.delete("/{loan_id}")
    async def remove_loan(
        loan_id: str,
        member: CompanyMember = Depends(require_role([MemberRole.OWNER, MemberRole.ADMIN, MemberRole.ACCOUNTANT])),
        db: AsyncSession = Depends(get_db),
    ): ...

Если у юзера ещё нет CompanyMember-строки (legacy owner — он сам создал компанию)
— подразумеваем OWNER (он сам компанию создал).
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.models.team import CompanyMember, MemberRole, MemberStatus


# Удобные пресеты
ROLES_OWNER_ONLY = [MemberRole.OWNER]
ROLES_OWNER_ADMIN = [MemberRole.OWNER, MemberRole.ADMIN]
ROLES_WRITE = [
    MemberRole.OWNER, MemberRole.ADMIN, MemberRole.MANAGER, MemberRole.ACCOUNTANT,
]
ROLES_FINANCE = [
    MemberRole.OWNER, MemberRole.ADMIN, MemberRole.ACCOUNTANT,
]
ROLES_OPERATIONAL = [
    MemberRole.OWNER, MemberRole.ADMIN, MemberRole.MANAGER,
]


async def get_current_role(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemberRole:
    """Текущая роль юзера в его company. OWNER по умолчанию (legacy)."""
    cm = (await db.execute(
        select(CompanyMember).where(
            CompanyMember.user_id == current_user.id,
            CompanyMember.company_id == current_user.company_id,
            CompanyMember.status == MemberStatus.ACTIVE.value,
        )
    )).scalar_one_or_none()
    if not cm:
        # Legacy: юзер сам создал компанию — нет строки в company_members.
        return MemberRole.OWNER
    try:
        return MemberRole(cm.role)
    except ValueError:
        return MemberRole.VIEWER


def require_role(allowed: list[MemberRole]):
    """Зависимость FastAPI: разрешает только определённые роли."""
    allowed_values = {r.value for r in allowed}

    async def _check(role: MemberRole = Depends(get_current_role)) -> MemberRole:
        if role.value not in allowed_values:
            raise HTTPException(
                403,
                detail=f"Недостаточно прав. Нужна роль: {', '.join(sorted(allowed_values))}. У вас: {role.value}",
            )
        return role

    return _check


# Шорткаты для удобства
require_owner = require_role(ROLES_OWNER_ONLY)
require_admin = require_role(ROLES_OWNER_ADMIN)
require_write = require_role(ROLES_WRITE)
require_finance = require_role(ROLES_FINANCE)
require_operational = require_role(ROLES_OPERATIONAL)
