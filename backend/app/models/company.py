"""
Модели для мультитенантности и пользователей.

Структура:
- Company (компания/клиент сервиса)
  - имеет много User (сотрудников)
  - имеет много OzonAccount (магазинов Озона)
- User (пользователь)
  - принадлежит одной Company
  - имеет одну Role
- Role (роль) — owner / manager / analyst / accountant / viewer
"""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, SoftDeleteMixin


class RoleName(str, Enum):
    """5 ролей в системе."""

    OWNER = "owner"          # полные права + биллинг
    MANAGER = "manager"      # управление товарами, ценами, рекламой
    ANALYST = "analyst"      # просмотр + создание отчётов
    ACCOUNTANT = "accountant"  # финансы, налоги, кредиты
    VIEWER = "viewer"        # только просмотр


class Role(BaseModel):
    """Роль с правами."""

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Права в формате JSON: {"products.edit": true, "finance.view": true, ...}
    permissions: Mapped[dict] = mapped_column(JSON, default=dict)

    # Связи
    users: Mapped[list["User"]] = relationship(back_populates="role")


class Company(BaseModel, SoftDeleteMixin):
    """
    Компания/клиент сервиса.

    Это корень мультитенантности — все данные привязаны к company_id.
    Один пользователь = одна компания (для простоты MVP).
    Потом можно сделать user_companies (many-to-many).
    """

    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    inn: Mapped[str | None] = mapped_column(String(12), unique=True, nullable=True)

    # Тариф подписки
    subscription_tier: Mapped[str] = mapped_column(
        String(50), default="free", nullable=False
    )
    subscription_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # === НАЛОГОВЫЙ РЕЖИМ ===
    # Применяется к чистой прибыли в Экономике/P&L/Cashflow.
    # 'usn_income'        — УСН Доходы (% от выручки, обычно 6%)
    # 'usn_income_minus'  — УСН Доходы-Расходы (% от прибыли, обычно 15%)
    # 'osno'              — ОСНО на прибыль (20%) + НДС
    # 'none'              — без налога (для тестов)
    tax_regime: Mapped[str] = mapped_column(
        String(20), default="usn_income", server_default="usn_income", nullable=False
    )
    tax_rate_pct: Mapped[float] = mapped_column(
        Numeric(5, 2), default=6.0, server_default="6.0", nullable=False
    )
    vat_rate_pct: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )  # NULL = НДС не применяем (УСН), 20 = стандарт ОСНО, 10/5/0 — льготные

    # Связи
    users: Mapped[list["User"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    ozon_accounts: Mapped[list["OzonAccount"]] = relationship(  # noqa: F821
        back_populates="company", cascade="all, delete-orphan"
    )


class User(BaseModel, SoftDeleteMixin):
    """Пользователь компании."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
    )

    # Связь с компанией (мультитенантность)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Связь с ролью
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Учётка
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Статус
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Owner of the system Pro-кабинета (видит market_* данные и системные настройки)
    is_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    # Метаданные
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Уведомления
    telegram_chat_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notification_preferences: Mapped[dict] = mapped_column(JSON, default=dict)

    # Связи
    company: Mapped[Company] = relationship(back_populates="users")
    role: Mapped[Role] = relationship(back_populates="users")
