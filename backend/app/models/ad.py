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
        Index("ix_ad_campaigns_user", "user_id"),
    )

    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ID кампании в Ozon (string в API, но реально число)
    ozon_campaign_id: Mapped[str] = mapped_column(String(50), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    campaign_type: Mapped[str] = mapped_column(
        String(64), default=AdCampaignType.UNKNOWN.value, nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(64), default=AdCampaignState.UNKNOWN.value, nullable=False
    )

    # from_date/to_date оставляем для обратной совместимости; start_date/end_date — каноничные.
    from_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    to_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    daily_budget: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    weekly_budget: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    budget: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    created_at_ozon: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Полный raw-ответ кампании из API — для разбора того, что мы пока не кладём в колонки
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)


class AdCampaignProduct(BaseModel):
    """Товары внутри кампании со ставкой / группой."""

    __tablename__ = "ad_campaign_products"
    __table_args__ = (
        Index("ix_ad_campaign_products_campaign", "campaign_id"),
        Index("ix_ad_campaign_products_product", "product_id"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ad_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )
    bid: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    group_id: Mapped[str | None] = mapped_column(String(50), nullable=True)


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
        Index("ix_ad_statistics_user", "user_id"),
        Index("ix_ad_statistics_product", "product_id"),
    )

    date: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    ozon_campaign_id: Mapped[str] = mapped_column(
        String(50), primary_key=True, nullable=False
    )
    # Опциональный product_id попадает в составной PK, чтобы хранить разбивку
    # «кампания×товар» в hypertable; для агрегатов на уровне кампании используем
    # NIL UUID (00000000-0000-0000-0000-000000000000).
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False
    )

    # Денормализация для быстрых per-account запросов без джойна на кампанию
    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Метрики
    impressions: Mapped[int] = mapped_column(BigInteger, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    spend: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    # CTR (clicks/impressions), ДРР (spend/revenue), ROAS (revenue/spend)
    ctr: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    drr: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    roas: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    avg_bid: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)

    # Технические
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
