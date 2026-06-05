"""
Модели для подключения к Озону.

- OzonAccount: один магазин Озона (у пользователя их может быть несколько)
- SyncLog: лог синхронизаций с Озоном (важно для отладки)

ВАЖНО: API ключи Озона ХРАНЯТСЯ ЗАШИФРОВАННЫМИ (через app.core.security.encrypt_secret)
"""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, SoftDeleteMixin


class OzonAccountStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"  # ошибка авторизации
    SYNCING = "syncing"


class OzonPremiumTier(str, Enum):
    """Уровень подписки селлера на Ozon.

    Определяет какие API-эндпоинты доступны для синхронизации.
    Юзер выбирает уровень вручную при подключении кабинета.
    """

    FREE = "free"
    PREMIUM = "premium"  # 5990₽/мес — API-привилегий не даёт, эквивалент FREE
    PREMIUM_PLUS = "premium_plus"  # 24990₽ — конкуренты (8), расширенная аналитика, реализация
    PREMIUM_PRO = "premium_pro"  # 24990₽ + 2.5% — всё выше + отзывы, поиск, конкуренты без лимита


class OzonAccount(BaseModel, SoftDeleteMixin):
    """
    Магазин Озона.

    У одной Company может быть несколько магазинов (у тебя их 4).
    Каждый магазин имеет свои API ключи (Seller + Performance) и свой premium-тариф.
    """

    __tablename__ = "ozon_accounts"

    # Связь с компанией (мультитенантность)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Идентификация магазина
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # API ключи (ЗАШИФРОВАНЫ через Fernet)
    # Seller API
    client_id_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    # Performance API (для рекламы) — опционально
    perf_client_id_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    perf_client_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Кэш access_token: получается из POST /api/client/token, живёт ~30 минут
    perf_access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    perf_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Тариф селлера на Ozon — управляет тем, какие API-методы доступны
    premium_tier: Mapped[str] = mapped_column(
        String(20),
        default=OzonPremiumTier.FREE.value,
        server_default=OzonPremiumTier.FREE.value,
        nullable=False,
    )

    # is_system=true → данные этого кабинета идут в market_* (общие данные рынка).
    # Заполнять только из админ-кабинета Flowoi. Юзерские кабинеты — всегда false.
    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    # Статус
    status: Mapped[str] = mapped_column(
        String(20),
        default=OzonAccountStatus.ACTIVE.value,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Синхронизация
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Метаданные с Озона (заполняется при синхронизации)
    seller_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    # === Налоги per-cabinet ===
    # Переопределяет company-level настройки. NULL = брать из Company.
    # Один селлер может иметь кабинет в льготном регионе (УСН 1%) и
    # другой в обычном (ОСНО 20% + НДС 22% возвратный).
    tax_regime: Mapped[str | None] = mapped_column(String(30), nullable=True)
    tax_rate_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    # НДС-ставка отдельно. На УСН с доходом >60млн в 2025 году НДС 5% обязателен.
    vat_rate_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    # vat_refundable=True → ОСНО, можно вычитать входной НДС.
    # vat_refundable=False → УСН с НДС 5%/7% — входной НДС не возвращается, фактически расход.
    vat_refundable: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False,
    )
    # Свободный комментарий: «Калмыкия УСН 1%», «Москва ОСНО»
    tax_region_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Связи
    company = relationship("Company", back_populates="ozon_accounts")
    sync_logs: Mapped[list["SyncLog"]] = relationship(
        back_populates="ozon_account", cascade="all, delete-orphan"
    )


class SyncStatus(str, Enum):
    """Статус синхронизации."""

    STARTED = "started"
    SUCCESS = "success"
    PARTIAL = "partial"  # частичный успех (что-то загрузилось, что-то нет)
    FAILED = "failed"


class SyncLog(BaseModel):
    """
    Лог каждой синхронизации с Озоном.

    Зачем:
    - Видеть когда Озон API упал
    - Какие данные не загрузились
    - Сколько времени заняла синхронизация
    - Сколько записей обработано
    """

    __tablename__ = "sync_logs"

    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Что синхронизировали
    method: Mapped[str] = mapped_column(String(100), nullable=False)
    # например: "sync_products", "sync_orders", "sync_transactions"

    # Статус
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    # Тайминги
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Статистика
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)

    # Ошибки
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Связи
    ozon_account: Mapped[OzonAccount] = relationship(back_populates="sync_logs")
