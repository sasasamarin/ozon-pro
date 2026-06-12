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

from pydantic import BaseModel, model_validator


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

    @model_validator(mode='before')
    @classmethod
    def _normalize(cls, v):
        if isinstance(v, dict):
            if 'sku_id' in v and 'sku' not in v:
                v['sku'] = v['sku_id']
            if 'locked' in v and 'is_locked' not in v:
                v['is_locked'] = v['locked']
            # если передан список items — берём первый
            if 'items' in v and isinstance(v['items'], list) and len(v['items']) > 0:
                return cls._normalize(v['items'][0])
        return v


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
    cabinet_id: Optional[str] = None
    skus: list[str] = []
    metric_code: Literal["revenue", "orders", "units", "margin"]
    analysis_start: date
    analysis_end: date
    forecast_start: date
    forecast_end: date

    @model_validator(mode='before')
    @classmethod
    def _accept_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if 'cabinet_ids' in data and 'cabinet_id' not in data:
            ids = data.pop('cabinet_ids')
            if isinstance(ids, list) and ids:
                data['cabinet_id'] = ids[0]
        if 'metric' in data and 'metric_code' not in data:
            data['metric_code'] = data.pop('metric')
        if 'analysis_from' in data and 'analysis_start' not in data:
            data['analysis_start'] = data.pop('analysis_from')
        if 'analysis_to' in data and 'analysis_end' not in data:
            data['analysis_end'] = data.pop('analysis_to')
        if 'forecast_from' in data and 'forecast_start' not in data:
            data['forecast_start'] = data.pop('forecast_from')
        if 'forecast_to' in data and 'forecast_end' not in data:
            data['forecast_end'] = data.pop('forecast_to')
        return data


class ChartPoint(BaseModel):
    date: str
    value: float


class ForecastSkuItem(BaseModel):
    sku_id: str
    offer_id: str
    name: str
    cabinet_id: str
    fact: float
    forecast: float
    season_weights: list[float]
    reliability: Literal["low", "medium", "high"]


class ForecastResponse(BaseModel):
    items: list[ForecastSkuItem]
    history: list[ChartPoint]
    forecast_series: list[ChartPoint]


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

class FactRowOut(BaseModel):
    metric: str
    label: str
    fact: float
    plan: Optional[float] = None
    pro_rata: Optional[float] = None  # план × (прошло / всего)
    pct: Optional[float] = None       # факт / pro_rata × 100
    run_rate: Optional[float] = None  # факт / прошло × всего (прогноз на конец)


class FactVsPlanRow(BaseModel):
    plan_id: Optional[str] = None
    period_from: str
    period_to: str
    total_days: int
    days_passed: int
    rows: list[FactRowOut]


# ── Bridge waterfall ──────────────────────────────────────────────────────────

class BridgeItem(BaseModel):
    label: str
    value: float
    pct: float
    estimated: bool
    color: str  # 'positive' | 'negative' | 'neutral'


class BridgeResponse(BaseModel):
    base: float
    actual: float
    delta: float
    items: list[BridgeItem]
    check_delta: float
