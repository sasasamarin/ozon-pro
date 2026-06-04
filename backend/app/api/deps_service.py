"""
Service-token dependency для cross-service AI bridge.

AI-сервис (ozon-pro-ai на Render) ходит в этот API с заголовком
`Authorization: Bearer <SERVICE_TOKEN>`. Никаких user-JWT — это
machine-to-machine.

Возвращает фейк-User с company_id из SERVICE_DEFAULT_COMPANY_ID
для переиспользования существующих endpoint-helpers, которые
ожидают current_user.company_id.

Если SERVICE_TOKEN пустой или не совпадает — 401.
"""
from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models import User


async def verify_service_token(
    authorization: str = Header(default=""),
) -> bool:
    """Проверяет Bearer SERVICE_TOKEN. 401 если не задан/не совпадает."""
    if not settings.SERVICE_TOKEN:
        raise HTTPException(503, "SERVICE_TOKEN не задан на сервере")
    expected = f"Bearer {settings.SERVICE_TOKEN}"
    if authorization != expected:
        raise HTTPException(401, "Invalid service token")
    return True


async def get_service_user(
    _: bool = Depends(verify_service_token),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Возвращает first active User из дефолтной компании (или first из DB).
    Используется как стенд-ин для current_user в bridge-endpoints.

    SERVICE_DEFAULT_COMPANY_ID лучше задать в env — тогда AI всегда работает
    в нужной компании. Иначе берём первого юзера в системе.
    """
    if settings.SERVICE_DEFAULT_COMPANY_ID:
        try:
            cid = uuid.UUID(settings.SERVICE_DEFAULT_COMPANY_ID)
        except ValueError:
            raise HTTPException(500, "SERVICE_DEFAULT_COMPANY_ID не UUID")
        u = (await db.execute(
            select(User).where(User.company_id == cid, User.is_active.is_(True)).limit(1)
        )).scalar_one_or_none()
        if not u:
            raise HTTPException(404, "Нет active юзера в SERVICE_DEFAULT_COMPANY_ID")
        return u

    # Fallback — любой active user
    u = (await db.execute(
        select(User).where(User.is_active.is_(True)).limit(1)
    )).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "Нет active юзеров в системе")
    return u
