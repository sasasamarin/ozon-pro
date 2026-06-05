"""
План продаж — модели.

Архитектура:
  SalesPlan (1) → SalesPlanItem (N) → SalesPlanDaily (N)
  SalesPlan (1) → PlanKPI (N)

scope_type:
  company   — план на всю компанию (все кабинеты)
  cabinet   — план на конкретный кабинет (scope_ref = ozon_account_id)
  category  — план на категорию (scope_ref = category)
  group     — пользовательская группа (scope_ref = group name)
  glue      — склейка SKU (scope_ref = glue_id)
  sku       — один товар (scope_ref = product_id)

metric_code:
  orders        — заказы шт
  revenue       — выручка ₽
  gross_profit  — маржинальная прибыль ₽
  net_profit    — чистая прибыль ₽
  units         — единицы доставлено

distribution_mode:
  proportional — share по истории
  manual       — заданы вручную
  seasonal     — pro-rata по сезонным весам

source_pref:
  operational  — оперативная модель (transactions)
  official     — официальный отчёт Ozon (realization)
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Numeric,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SalesPlan(Base):
    __tablename__ = "sales_plan"
    __table_args__ = (
        Index("ix_sales_plan_company_period", "company_id", "period_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metric_code: Mapped[str] = mapped_column(String(40), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    analysis_start: Mapped[date] = mapped_column(Date, nullable=False)
    analysis_end: Mapped[date] = mapped_column(Date, nullable=False)
    base_forecast: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    target_value: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    distribution_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="proportional"
    )
    source_pref: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="operational"
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="user"
    )
    # draft | active | archived (lifecycle статус)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="active"
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # === Шаблоны и rollover ===
    is_template: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    template_cabinet_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    manual_adjustment: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0"
    )
    workspace_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rolled_from_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    items: Mapped[list["SalesPlanItem"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan",
        order_by="SalesPlanItem.created_at",
    )
    kpis: Mapped[list["PlanKPI"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan",
    )


class SalesPlanItem(Base):
    __tablename__ = "sales_plan_item"
    __table_args__ = (Index("ix_sales_plan_item_plan", "plan_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_plan.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    glue_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    analysis_value: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0"
    )
    share_pct: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, server_default="0"
    )
    plan_value: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0"
    )
    is_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    plan: Mapped[SalesPlan] = relationship(back_populates="items")
    daily: Mapped[list["SalesPlanDaily"]] = relationship(
        back_populates="item", cascade="all, delete-orphan",
        order_by="SalesPlanDaily.date",
    )


class SalesPlanDaily(Base):
    __tablename__ = "sales_plan_daily"
    __table_args__ = (
        UniqueConstraint("plan_item_id", "date", name="uq_plan_daily_item_date"),
        Index("ix_plan_daily_date", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    plan_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_plan_item.id", ondelete="CASCADE"),
        nullable=False,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    plan_value: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0"
    )
    season_weight: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, server_default="0"
    )

    item: Mapped[SalesPlanItem] = relationship(back_populates="daily")


class PlanKPI(Base):
    __tablename__ = "plan_kpi"
    __table_args__ = (Index("ix_plan_kpi_plan", "plan_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_plan.id", ondelete="CASCADE"),
        nullable=False,
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    manager_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metric_code: Mapped[str] = mapped_column(String(40), nullable=False)
    target_value: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    # {"model": "A", "pct_of_net": 5} или {"model": "B", "thresholds": [{"at":100,"bonus":10000}]}
    bonus_rule: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    plan: Mapped[SalesPlan] = relationship(back_populates="kpis")
