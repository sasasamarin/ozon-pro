"""
monthly_unit_economy — точные per-product финансы из XLSX «Экономика магазина».

Источник истины — выгрузка из кабинета Ozon (Финансы → Экономика магазина →
Общие расходы → XLSX). API публичного этого не отдаёт — проверено 19 endpoint'ов.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MonthlyUnitEconomy(Base):
    __tablename__ = "monthly_unit_economy"

    cabinet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ozon_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    sku: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    month: Mapped[date] = mapped_column(Date, primary_key=True)

    period_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    offer_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheme: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)

    ordered_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivered_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    returned_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Доходы (+)
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    spp_points: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    partner_programs: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)

    # Расходы (отрицательные числа из файла — знак сохраняется как в Ozon)
    ozon_commission: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    acquiring: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    posting_handling: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    logistics: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    last_mile: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    storage: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    return_handling: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    reverse_logistics: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    disposal: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    ovh_extra: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    operational_errors: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)

    # Реклама по видам (отдельные колонки в Ozon XLSX)
    ad_cpc: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    ad_cpo: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    ad_star: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    ad_paid_brand: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    ad_reviews: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)

    # Расчётные поля Ozon — для сверки нашей формулы (juзнит-тест)
    ozon_profit: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    ozon_margin_share: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    price_index: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)

    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    source_file: Mapped[str | None] = mapped_column(Text, nullable=True)
