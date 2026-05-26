"""
Базовый класс для всех моделей БД.

Все модели наследуются от Base и получают:
- id (UUID)
- created_at, updated_at
- soft delete (deleted_at)
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


# Соглашение об именах для constraints (важно для миграций Alembic)
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Соглашение: имя таблицы — snake_case множественное число
    @classmethod
    def __declare_last__(cls) -> None:  # pragma: no cover
        pass


class UUIDMixin:
    """UUID первичный ключ (используем вместо int для безопасности и масштабирования)."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )


class TimestampMixin:
    """Поля created_at, updated_at — есть у всех записей."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """
    Мягкое удаление: помечаем deleted_at вместо физического удаления.

    Используется для всех важных таблиц (Product, Marker, OzonAccount).
    Никогда не удаляем физически — для финансового учёта и истории.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class BaseModel(Base, UUIDMixin, TimestampMixin):
    """
    Базовая модель для большинства сущностей.
    Включает UUID и timestamps.
    """

    __abstract__ = True

    def to_dict(self) -> dict[str, Any]:
        """Конвертировать в словарь (для API ответов)."""
        return {
            c.name: getattr(self, c.name)
            for c in self.__table__.columns
        }


class TenantModel(BaseModel):
    """
    Базовая модель для мультитенантных сущностей.

    Все таблицы которые принадлежат компании (Company) наследуются отсюда.
    Это обеспечивает изоляцию данных между клиентами сервиса.
    """

    __abstract__ = True

    # company_id обязательное поле, задаётся в подклассе через ForeignKey
    # (нельзя в Mixin потому что Alembic путается с импортами)
