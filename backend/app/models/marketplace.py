"""
Сущности маркетплейса Ozon, которые не относятся ни к заказам, ни к финансам:
- Return: возврат от покупателя
- RealizationLine: позиция отчёта о реализации за период (Premium Plus+)
- Review: отзыв на товар (Premium Pro)
- Question: вопрос на товар (Premium Pro)
"""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class Return(BaseModel):
    """
    Возврат от покупателя.

    Получаем через /v3/returns/list. Может быть привязан к posting (отправлению)
    или быть независимым (например, возврат от невыкупа).
    """

    __tablename__ = "returns"
    __table_args__ = (
        UniqueConstraint(
            "ozon_account_id", "ozon_return_id", name="uq_returns_account_return"
        ),
        Index("ix_returns_account_date", "ozon_account_id", "return_date"),
    )

    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ID возврата у Ozon
    ozon_return_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    posting_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    ozon_sku: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Тип / причина / сумма / статус
    return_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    return_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_amount: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Тайминги
    return_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    moved_to_warehouse_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)


class RealizationLine(BaseModel):
    """
    Одна позиция отчёта о реализации за период.

    Получаем через /v2/finance/realization. Один отчёт = много позиций.
    Денормализованная структура: каждый row уже знает свой период.

    Требует premium_tier ∈ {premium_plus, premium_pro}.
    """

    __tablename__ = "realization_lines"
    __table_args__ = (
        UniqueConstraint(
            "ozon_account_id",
            "period_from",
            "period_to",
            "ozon_sku",
            name="uq_realization_account_period_sku",
        ),
        Index("ix_realization_account_period", "ozon_account_id", "period_from", "period_to"),
    )

    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)

    ozon_sku: Mapped[int] = mapped_column(BigInteger, nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    offer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)

    qty_sold: Mapped[int] = mapped_column(Integer, default=0)
    qty_returned: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    commission_amount: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    delivery_amount: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    refund_amount: Mapped[float] = mapped_column(Numeric(15, 2), default=0)

    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)


class Review(BaseModel):
    """
    Отзыв на товар.

    Требует premium_tier == premium_pro (отзывы доступны только на Pro).
    Получаем через /v1/review/list.
    """

    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint(
            "ozon_account_id", "ozon_review_id", name="uq_reviews_account_review"
        ),
        Index("ix_reviews_account_date", "ozon_account_id", "review_date"),
        Index("ix_reviews_sku", "ozon_sku"),
    )

    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    ozon_review_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ozon_sku: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    review_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    pluses: Mapped[str | None] = mapped_column(Text, nullable=True)
    minuses: Mapped[str | None] = mapped_column(Text, nullable=True)

    review_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    has_response: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_photos: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_videos: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)


class Question(BaseModel):
    """
    Вопрос на товар.

    Требует premium_tier == premium_pro.
    """

    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint(
            "ozon_account_id", "ozon_question_id", name="uq_questions_account_question"
        ),
        Index("ix_questions_account_date", "ozon_account_id", "question_date"),
        Index("ix_questions_sku", "ozon_sku"),
    )

    ozon_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    ozon_question_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ozon_sku: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    question_text: Mapped[str | None] = mapped_column(Text, nullable=False)
    question_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    status: Mapped[str | None] = mapped_column(String(30), nullable=True)

    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
