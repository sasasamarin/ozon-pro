"""
Модели: Product, PriceHistory, Stock.

- Product: товар Озона (привязан к OzonAccount)
- PriceHistory: история цен (TimescaleDB hypertable)
- Stock: остатки на складах (TimescaleDB hypertable)
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel, SoftDeleteMixin


class Product(BaseModel, SoftDeleteMixin):
    """Товар Озона."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint(
            "ozon_account_id", "ozon_sku", name="uq_products_account_sku"
        ),
        Index("ix_products_offer_id", "offer_id"),
    )

    # Мультитенантность через ozon_account
    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Идентификаторы Озона
    ozon_sku: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ozon_product_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    offer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    fbo_sku: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    fbs_sku: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Базовая информация
    name: Mapped[str] = mapped_column(Text, nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Цены (текущие, обновляются при синхронизации)
    cost_price: Mapped[float | None] = mapped_column(
        Numeric(15, 2), nullable=True
    )  # себестоимость (вводит юзер)
    current_price: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    old_price: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    marketing_price: Mapped[float | None] = mapped_column(
        Numeric(15, 2), nullable=True
    )  # цена для покупателя с СПП
    min_price: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)

    # Индекс цен
    price_index: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # "WITHOUT_INDEX" | "PROFIT" | "AVG_PROFIT" | "NON_PROFIT"

    # Статус
    visibility: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Свободные теги юзера (например "хит", "сезон", "новинка") + флаг 🔥
    tags: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default="[]", nullable=False
    )
    is_hot: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    # Рейтинг и отзывы
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)

    # Дополнительные данные с Озона (полный JSON)
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)

    # Связи
    ozon_account = relationship("OzonAccount")
    markers = relationship("Marker", back_populates="product")


# ============================================
# TIMESCALEDB HYPERTABLES (временные ряды)
# ============================================
# Эти таблицы должны быть превращены в hypertable через миграцию:
#   SELECT create_hypertable('price_history', 'time');


class PriceHistory(Base):
    """
    История цен товара (TimescaleDB hypertable).

    Снапшоты каждый час или при изменении.
    Храним за ГОДЫ (TimescaleDB автоматически сжимает старые данные).
    """

    __tablename__ = "price_history"
    __table_args__ = (
        # Композитный первичный ключ: time + product_id
        Index("ix_price_history_product_time", "product_id", "time"),
    )

    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    price: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    marketing_price: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    old_price: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    price_index: Mapped[str | None] = mapped_column(String(50), nullable=True)


class Stock(Base):
    """
    Остатки на складах (TimescaleDB hypertable).

    Снапшоты каждый час по каждому товару + складу + типу (FBO/FBS).
    """

    __tablename__ = "stocks"
    __table_args__ = (
        Index("ix_stocks_product_time", "product_id", "time"),
        Index("ix_stocks_warehouse", "warehouse_name"),
    )

    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    # Тип склада и название
    warehouse_type: Mapped[str] = mapped_column(
        String(20), primary_key=True, nullable=False
    )  # "FBO" | "FBS" | "FBO_WH"
    # warehouse_name входит в PK с alembic 0010, иначе ORM identity-map склеивает
    # все per-warehouse строки в одну (визуально 7 копий одного склада).
    # NULL → '<aggregate>' (для AGG/FBO/FBS/RFBS строк без конкретного склада).
    warehouse_name: Mapped[str] = mapped_column(
        String(255), primary_key=True, nullable=False, server_default="<aggregate>"
    )
    warehouse_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Остатки
    free_to_sell: Mapped[int] = mapped_column(Integer, default=0)  # доступно к продаже
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    in_transit: Mapped[int] = mapped_column(Integer, default=0)  # в пути

    # Кластер (регион)
    cluster: Mapped[str | None] = mapped_column(String(100), nullable=True)
