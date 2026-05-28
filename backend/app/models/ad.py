"""
Реклама Ozon: кампании и статистика из Performance API.

- AdCampaign: кампания (SKU / search / banner / brand_shelf) — одна строка на кампанию
- AdStatistics: статистика по кампании за день (TimescaleDB hypertable)
"""
import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModel


class AdCampaignType(str, Enum):
    """Типы рекламных кампаний Ozon Performance."""

    SKU = "sku"
    SEARCH = "search_promo"
    BANNER = "banner"
    BRAND_SHELF = "brand_shelf"
    UNKNOWN = "unknown"


class AdCampaignState(str, Enum):
    """Состояние кампании."""

    RUNNING = "running"
    PLANNED = "planned"
    PAUSED = "paused"
    FINISHED = "finished"
    ARCHIVED = "archived"
    UNKNOWN = "unknown"


class AdCampaign(BaseModel):
    """Рекламная кампания (Performance API)."""

    __tablename__ = "ad_campaigns"
    __table_args__ = (
        UniqueConstraint(
            "ozon_account_id", "ozon_campaign_id", name="uq_ad_campaigns_account_campaign"
        ),
        Index("ix_ad_campaigns_state", "state"),
    )

    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ID кампании в Ozon (string в API, но реально число)
    ozon_campaign_id: Mapped[str] = mapped_column(String(50), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    campaign_type: Mapped[str] = mapped_column(
        String(30), default=AdCampaignType.UNKNOWN.value, nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(20), default=AdCampaignState.UNKNOWN.value, nullable=False
    )

    from_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    to_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    daily_budget: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    weekly_budget: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    budget: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)

    # Полный raw-ответ кампании из API — для разбора того, что мы пока не кладём в колонки
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)


# ============================================
# TIMESCALEDB HYPERTABLE
# ============================================


class AdStatistics(Base):
    """
    Статистика по кампании за день (TimescaleDB hypertable).

    Поле `date` плюс ID кампании — составной PK, один день = один снимок на кампанию.
    Считаем ДРР = money_spent / revenue, ROAS = revenue / money_spent.
    """

    __tablename__ = "ad_statistics"
    __table_args__ = (
        Index("ix_ad_statistics_account_date", "ozon_account_id", "date"),
        Index("ix_ad_statistics_campaign_date", "ozon_campaign_id", "date"),
    )

    date: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    ozon_campaign_id: Mapped[str] = mapped_column(
        String(50), primary_key=True, nullable=False
    )

    # Денормализация для быстрых per-account запросов без джойна на кампанию
    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Метрики
    views: Mapped[int] = mapped_column(BigInteger, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    money_spent: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    # CTR (clicks/views), ДРР (money_spent/revenue) — храним для удобства запросов
    ctr: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    drr: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)

    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)

    # Технические
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
