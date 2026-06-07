from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel


class SalesPlanCreate(BaseModel):
    company_id: int
    scope_type: Literal["company", "cabinet", "category", "group", "glue", "sku"]
    scope_ref: Optional[str] = None
    metric_code: str
    period_start: date
    period_end: date
    target_value: Optional[Decimal] = None
    source_pref: Literal["operational", "official"]
    note: Optional[str] = None


class SalesPlanRow(BaseModel):
    id: int
    scope_type: str
    scope_ref: Optional[str]
    metric_code: str
    target_value: Optional[float]
    period_start: date
    period_end: date


class SalesPlanDetail(BaseModel):
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
