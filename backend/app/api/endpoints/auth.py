"""
Авторизация: регистрация, логин, refresh токенов.
"""
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.logging import log
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models import Company, Role, RoleName, User

router = APIRouter()


# === Pydantic схемы ===

class RegisterRequest(BaseModel):
    """Запрос на регистрацию."""
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    company_name: str = Field(min_length=2, max_length=255)


class LoginRequest(BaseModel):
    """Запрос на логин."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Ответ с токенами."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Информация о пользователе."""
    id: str
    email: str
    full_name: str | None
    company_id: str
    role: str

    class Config:
        from_attributes = True


# === Endpoints ===

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Регистрация нового пользователя + создание компании.

    Первый юзер компании автоматически получает роль OWNER.
    """
    # Проверка что email не занят
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email уже зарегистрирован",
        )

    # Создаём компанию
    company = Company(name=payload.company_name)
    db.add(company)
    await db.flush()

    # Получаем роль OWNER
    result = await db.execute(
        select(Role).where(Role.name == RoleName.OWNER.value)
    )
    owner_role = result.scalar_one_or_none()
    if not owner_role:
        # Если ролей ещё нет — создаём базовую
        owner_role = Role(
            name=RoleName.OWNER.value,
            description="Владелец компании",
            permissions={"*": True},
        )
        db.add(owner_role)
        await db.flush()

    # Создаём пользователя
    user = User(
        company_id=company.id,
        role_id=owner_role.id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        is_active=True,
        is_verified=False,  # потом подтвердит email
    )
    db.add(user)
    await db.flush()

    log.info("user_registered", user_id=str(user.id), company_id=str(company.id))

    # Возвращаем токены
    return TokenResponse(
        access_token=create_access_token(
            subject=str(user.id),
            extra_claims={"company_id": str(company.id), "role": owner_role.name},
        ),
        refresh_token=create_refresh_token(subject=str(user.id)),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Логин по email + паролю."""

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
        )

    if not user.is_active or user.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт заблокирован",
        )

    # Обновляем last_login
    user.last_login = datetime.now(UTC)

    # Загружаем роль
    result = await db.execute(select(Role).where(Role.id == user.role_id))
    role = result.scalar_one()

    log.info("user_logged_in", user_id=str(user.id))

    return TokenResponse(
        access_token=create_access_token(
            subject=str(user.id),
            extra_claims={"company_id": str(user.company_id), "role": role.name},
        ),
        refresh_token=create_refresh_token(subject=str(user.id)),
    )


# ============================================================
# /me — current user info + profile update
# ============================================================


class MeResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    company_id: str
    company_name: str | None
    role: str
    is_admin: bool


class MeUpdateRequest(BaseModel):
    """Edit-profile payload. Email пока не редактируется (нужна верификация — отдельно)."""

    full_name: str | None = None


async def _build_me_response(user: User, db: AsyncSession) -> MeResponse:
    # Роль из CompanyMember (новый RBAC). Если строки нет — юзер сам создал
    # компанию, считаем OWNER (legacy совместимость).
    from app.models.team import CompanyMember, MemberRole, MemberStatus
    cm = (await db.execute(
        select(CompanyMember).where(
            CompanyMember.user_id == user.id,
            CompanyMember.company_id == user.company_id,
            CompanyMember.status == MemberStatus.ACTIVE.value,
        )
    )).scalar_one_or_none()
    role_name = cm.role if cm else MemberRole.OWNER.value

    company = (
        await db.execute(select(Company).where(Company.id == user.company_id))
    ).scalar_one_or_none()
    return MeResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        company_id=str(user.company_id),
        company_name=company.name if company else None,
        role=role_name,
        is_admin=user.is_admin,
    )


@router.get("/me", response_model=MeResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    """Текущий пользователь — для подгрузки профиля во фронт."""
    return await _build_me_response(current_user, db)


@router.patch("/me", response_model=MeResponse)
async def update_me(
    payload: MeUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    """Редактирование профиля — пока только full_name. Email — отдельно (верификация)."""
    if payload.full_name is not None:
        current_user.full_name = payload.full_name.strip() or None
    await db.flush()
    log.info("user_profile_updated", user_id=str(current_user.id))
    return await _build_me_response(current_user, db)
