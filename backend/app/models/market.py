"""
Market intelligence — общие данные рынка БЕЗ user_id.

Заполняются ТОЛЬКО синком из системного Pro-кабинета (ozon_accounts.is_system=true).
ТОЛЬКО публичные данные Ozon. Доступны всем пользователям по подписке.
Приватные данные сюда не попадают.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModel


class CrossPlatform(str, Enum):
    WILDBERRIES = "wildberries"
    YANDEX_MARKET = "yandex_market"
    MEGAMARKET = "megamarket"


class MarketCompetitor(BaseModel):
    """Селлер-конкурент в категории."""

    __tablename__ = "market_competitors"
    __table_args__ = (Index("ix_market_competitors_seller", "ozon_seller_id"),)

    ozon_seller_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)

    first_seen: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_seen: Mapped[date | None] = mapped_column(Date, nullable=True)


# ============================================================
# HYPERTABLE: market_competitor_prices
# ============================================================


class MarketCompetitorPrice(Base):
    """Снимок цены/остатка/позиции конкурента (TimescaleDB hypertable)."""

    __tablename__ = "market_competitor_prices"
    __table_args__ = (
        Index("ix_market_competitor_prices_competitor_time", "competitor_id", "time"),
        Index("ix_market_competitor_prices_sku", "ozon_sku"),
    )

    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("market_competitors.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    ozon_sku: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False)

    name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    old_price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    stock_present: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    search_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    reviews_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class MarketSearchQuery(BaseModel):
    """Популярные поисковые запросы (для категорий)."""

    __tablename__ = "market_search_queries"
    __table_args__ = (
        Index("ix_market_search_queries_query", "query"),
        Index("ix_market_search_queries_period", "period"),
    )

    query: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    frequency: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    # Формат "YYYY-MM" для месячных снимков
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    avg_price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)


class MarketCrossPlatform(BaseModel):
    """Цены/остатки конкурентов на ДРУГИХ площадках (Premium Pro only)."""

    __tablename__ = "market_cross_platform"
    __table_args__ = (
        Index("ix_market_cross_competitor_platform", "competitor_name", "platform"),
    )

    competitor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(30), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    stock: Mapped[int | None] = mapped_column(Integer, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


# ============================================================
# HYPERTABLE: market_trends_daily
# ============================================================


class MarketTrendsDaily(Base):
    """
    Ежедневные тренды по категориям (TimescaleDB hypertable).

    seasonal_index — питает forecasting.velocity у юзеров,
    которые ещё не накопили своей годовой истории.
    """

    __tablename__ = "market_trends_daily"
    __table_args__ = (
        Index("ix_market_trends_category_time", "category", "time"),
    )

    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    category: Mapped[str] = mapped_column(String(255), primary_key=True, nullable=False)

    demand_index: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    avg_price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    growth_rate: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    new_products_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seasonal_index: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
