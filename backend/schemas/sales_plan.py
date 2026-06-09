from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, model_validator


class SalesPlanCreate(BaseModel):
    company_id: Optional[Any] = None
    scope_type: Literal["company", "cabinet", "category", "group", "glue", "sku"] = "company"
    scope_ref: Optional[str] = None
    metric_code: str = "orders"
    period_start: date
    period_end: date
    target_value: Optional[Decimal] = None
    source_pref: Literal["operational", "official"] = "operational"
    note: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if 'metric' in data and 'metric_code' not in data:
            data['metric_code'] = data.pop('metric')
        if 'period_from' in data and 'period_start' not in data:
            data['period_start'] = data.pop('period_from')
        if 'period_to' in data and 'period_end' not in data:
            data['period_end'] = data.pop('period_to')
        if 'cabinet_ids' in data:
            ids = data.pop('cabinet_ids')
            if 'scope_type' not in data:
                if isinstance(ids, list) and ids:
                    data['scope_type'] = 'cabinet'
                    data.setdefault('scope_ref', ids[0])
                else:
                    data['scope_type'] = 'company'
        data.setdefault('source_pref', 'operational')
        return data


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
