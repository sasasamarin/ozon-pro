"""
Pydantic-схемы для раздела «План продаж».

Примечание: company_id в таблице sales_plan — int (по спецификации миграции).
В остальной системе company_id — UUID. Несоответствие нужно исправить
отдельной миграцией.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel


# ── Планы ──────────────────────────────────────────────────────────────────

class PlanCreate(BaseModel):
    company_id: int
    scope_type: Literal["company", "cabinet", "category", "group", "glue", "sku"]
    scope_ref: Optional[str] = None
    metric_code: str
    period_start: date
    period_end: date
    analysis_start: Optional[date] = None
    analysis_end: Optional[date] = None
    target_value: Optional[Decimal] = None
    distribution_mode: Literal["proportional", "manual", "seasonal"] = "proportional"
    source_pref: Literal["operational", "official"] = "operational"
    note: Optional[str] = None


class PlanOut(BaseModel):
    id: int
    company_id: int
    scope_type: str
    scope_ref: Optional[str]
    metric_code: str
    period_start: date
    period_end: date
    analysis_start: Optional[date]
    analysis_end: Optional[date]
    base_forecast: Optional[float]
    target_value: Optional[float]
    distribution_mode: str
    source_pref: str
    note: Optional[str]
    source: str
    created_at: datetime
    updated_at: datetime


# ── Позиции плана ───────────────────────────────────────────────────────────

class PlanItemCreate(BaseModel):
    sku: str
    plan_value: float
    is_locked: bool = False


class PlanItemUpdate(BaseModel):
    plan_value: Optional[float] = None
    is_locked: Optional[bool] = None


class PlanItemOut(BaseModel):
    id: int
    plan_id: int
    sku: Optional[str]
    glue_id: Optional[int]
    analysis_value: Optional[float]
    share_pct: Optional[float]
    plan_value: Optional[float]
    is_locked: bool


# ── Посуточное распределение ────────────────────────────────────────────────

class PlanDailyOut(BaseModel):
    id: int
    plan_item_id: int
    date: date
    plan_value: Optional[float]
    season_weight: Optional[float]


# ── KPI ─────────────────────────────────────────────────────────────────────

class PlanKpiOut(BaseModel):
    id: int
    plan_id: int
    manager_id: Optional[int]
    metric_code: str
    target_value: Optional[float]
    bonus_rule: Optional[dict]


# ── Прогноз ─────────────────────────────────────────────────────────────────

class ForecastRequest(BaseModel):
    cabinet_id: uuid.UUID
    skus: list[str] = []
    metric_code: Literal["revenue", "orders", "units", "margin"]
    analysis_start: date
    analysis_end: date
    forecast_start: date
    forecast_end: date


class ForecastResponse(BaseModel):
    cabinet_id: str
    metric_code: str
    dates: list[str]
    history: list[Optional[float]]
    base_forecast: list[float]
    total_forecast: float
    r2: float
    data_points_count: int
    badge: Literal["low", "medium", "high"]


# ── Каскадный симулятор ──────────────────────────────────────────────────────

class SimulateRequest(BaseModel):
    plan_id: int
    metric: str
    delta: float


class SimulateResponse(BaseModel):
    plan_id: int
    metric: str
    delta: float
    cascade: dict[str, Any]
    sources: dict[str, str]


# ── Факт vs план ─────────────────────────────────────────────────────────────

class FactVsPlanRow(BaseModel):
    metric: str
    plan: Optional[float]
    fact: Optional[float]
    plan_pct: Optional[float]         # факт / план %
    pro_rata: Optional[float]         # план × (прошло дней / всего дней)
    run_rate: Optional[float]         # факт / прошло × всего дней (прогноз на конец)
    needed_per_day: Optional[float]   # (план − факт) / оставшиеся дни
    source: str                       # 'operational' | 'official'
    delta_realization: Optional[str]  # realization − transactions строкой (если оба есть)
