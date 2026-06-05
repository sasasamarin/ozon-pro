"""
/api/v1/plans — план продаж (новый раздел).

Endpoints:
  POST   /plans/forecast              — посчитать прогноз без сохранения
  POST   /plans/distribute            — распределить target по SKU
  POST   /plans                       — создать план (с items + daily)
  GET    /plans                       — список планов компании
  GET    /plans/{plan_id}             — детальный
  PATCH  /plans/{plan_id}             — обновить (метаданные / target)
  DELETE /plans/{plan_id}             — удалить
  PATCH  /plans/{plan_id}/items/{id}  — править item (plan_value/is_locked)
  POST   /plans/{plan_id}/rebalance   — пересчёт долей без lock-нутых
  POST   /plans/{plan_id}/distribute-days — рассчитать daily values
  POST   /plans/simulate              — симуляция каскада «+delta к метрике»
  GET    /plans/{plan_id}/fact        — факт + bridge + run-rate
  POST   /plans/{plan_id}/kpi         — назначить KPI менеджеру
  GET    /plans/{plan_id}/kpi         — список KPI плана
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.models.sales_plan import PlanKPI, SalesPlan, SalesPlanDaily, SalesPlanItem
from app.services.sales_plan.cascade import simulate_plan_change
from app.services.sales_plan.fact import compute_fact
from app.services.sales_plan.forecast import (
    compute_forecast, distribute_by_sku, fetch_history,
)


router = APIRouter()


# ============================================
# Schemas
# ============================================

class ForecastRequest(BaseModel):
    metric: str
    analysis_start: date
    analysis_end: date
    forecast_start: date
    forecast_end: date
    target_value: float | None = None
    cabinet_id: str | None = None
    product_id: str | None = None


class ForecastPoint(BaseModel):
    date: str
    value: float


class ForecastResponse(BaseModel):
    metric: str
    history: list[ForecastPoint]
    base_forecast: float
    forecast_series: list[ForecastPoint]
    modified_series: list[ForecastPoint] | None
    season_weights: dict[str, float]
    reliability: str
    reliability_pct: float
    note: str


class DistributeRequest(BaseModel):
    metric: str
    analysis_start: date
    analysis_end: date
    target_value: float
    cabinet_id: str | None = None


class DistributeItem(BaseModel):
    product_id: str | None
    sku: str | None
    name: str | None
    offer_id: str | None
    analysis_value: float
    share_pct: float
    plan_value: float


class PlanCreate(BaseModel):
    name: str
    scope_type: str
    scope_ref: str | None = None
    metric_code: str
    period_start: date
    period_end: date
    analysis_start: date
    analysis_end: date
    target_value: float
    base_forecast: float | None = None
    distribution_mode: str = "proportional"
    source_pref: str = "operational"
    note: str | None = None
    items: list[DistributeItem] = []


class PlanItemRow(BaseModel):
    id: str
    product_id: str | None
    sku: str | None
    name: str | None
    offer_id: str | None
    analysis_value: float
    share_pct: float
    plan_value: float
    is_locked: bool


class PlanRow(BaseModel):
    id: str
    name: str
    scope_type: str
    scope_ref: str | None
    metric_code: str
    period_start: str
    period_end: str
    analysis_start: str
    analysis_end: str
    target_value: float
    base_forecast: float | None
    distribution_mode: str
    source_pref: str
    note: str | None
    created_at: str
    items_count: int


class PlanDetail(PlanRow):
    items: list[PlanItemRow]


class PlanUpdate(BaseModel):
    name: str | None = None
    target_value: float | None = None
    distribution_mode: str | None = None
    note: str | None = None


class ItemUpdate(BaseModel):
    plan_value: float | None = None
    is_locked: bool | None = None


class SimulateRequest(BaseModel):
    metric: str
    delta: float
    period_start: date | None = None
    period_end: date | None = None
    cabinet_id: str | None = None


class KPICreate(BaseModel):
    manager_name: str
    metric_code: str
    target_value: float
    bonus_rule: dict | None = None


# ============================================
# Helpers
# ============================================

async def _get_plan_owned(
    db: AsyncSession, plan_id: uuid.UUID, company_id: uuid.UUID,
) -> SalesPlan:
    plan = (await db.execute(
        select(SalesPlan).where(
            SalesPlan.id == plan_id, SalesPlan.company_id == company_id,
        )
    )).scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "План не найден")
    return plan


def _plan_to_row(plan: SalesPlan, items_count: int = 0) -> PlanRow:
    return PlanRow(
        id=str(plan.id), name=plan.name,
        scope_type=plan.scope_type, scope_ref=plan.scope_ref,
        metric_code=plan.metric_code,
        period_start=plan.period_start.isoformat(),
        period_end=plan.period_end.isoformat(),
        analysis_start=plan.analysis_start.isoformat(),
        analysis_end=plan.analysis_end.isoformat(),
        target_value=float(plan.target_value),
        base_forecast=float(plan.base_forecast) if plan.base_forecast else None,
        distribution_mode=plan.distribution_mode,
        source_pref=plan.source_pref,
        note=plan.note,
        created_at=plan.created_at.isoformat(),
        items_count=items_count,
    )


def _item_to_row(item: SalesPlanItem, name: str | None = None) -> PlanItemRow:
    return PlanItemRow(
        id=str(item.id),
        product_id=str(item.product_id) if item.product_id else None,
        sku=item.sku,
        name=name,
        offer_id=item.sku,
        analysis_value=float(item.analysis_value),
        share_pct=float(item.share_pct),
        plan_value=float(item.plan_value),
        is_locked=item.is_locked,
    )


# ============================================
# Forecast / Distribute (без сохранения)
# ============================================

@router.post("/forecast", response_model=ForecastResponse)
async def forecast_plan(
    payload: ForecastRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ForecastResponse:
    """Прогноз метрики на forecast-период по истории analysis-периода."""
    cabinet = uuid.UUID(payload.cabinet_id) if payload.cabinet_id else None
    product = uuid.UUID(payload.product_id) if payload.product_id else None
    history = await fetch_history(
        db, company_id=current_user.company_id, metric=payload.metric,
        analysis_start=payload.analysis_start, analysis_end=payload.analysis_end,
        cabinet_id=cabinet, product_id=product,
    )
    result = compute_forecast(
        history, payload.forecast_start, payload.forecast_end, payload.target_value,
    )
    return ForecastResponse(
        metric=payload.metric,
        history=[ForecastPoint(date=d.isoformat(), value=v) for d, v in result.history],
        base_forecast=result.base_forecast,
        forecast_series=[ForecastPoint(date=d.isoformat(), value=v) for d, v in result.forecast_series],
        modified_series=[ForecastPoint(date=d.isoformat(), value=v) for d, v in result.modified_series] if result.modified_series else None,
        season_weights=result.season_weights,
        reliability=result.reliability,
        reliability_pct=result.reliability_pct,
        note=result.note,
    )


@router.post("/distribute", response_model=list[DistributeItem])
async def distribute_plan(
    payload: DistributeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DistributeItem]:
    """Распределить target по SKU пропорционально вкладу в analysis-периоде."""
    cabinet = uuid.UUID(payload.cabinet_id) if payload.cabinet_id else None
    items = await distribute_by_sku(
        db, company_id=current_user.company_id, metric=payload.metric,
        analysis_start=payload.analysis_start, analysis_end=payload.analysis_end,
        cabinet_id=cabinet, target_value=payload.target_value,
    )
    return [DistributeItem(**i) for i in items]


# ============================================
# CRUD планов
# ============================================

@router.post("", response_model=PlanDetail)
async def create_plan(
    payload: PlanCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlanDetail:
    """Создать план + сохранить items + (опционально) рассчитать daily."""
    plan = SalesPlan(
        company_id=current_user.company_id, user_id=current_user.id,
        name=payload.name, scope_type=payload.scope_type,
        scope_ref=payload.scope_ref, metric_code=payload.metric_code,
        period_start=payload.period_start, period_end=payload.period_end,
        analysis_start=payload.analysis_start, analysis_end=payload.analysis_end,
        target_value=Decimal(str(payload.target_value)),
        base_forecast=(Decimal(str(payload.base_forecast))
                       if payload.base_forecast is not None else None),
        distribution_mode=payload.distribution_mode,
        source_pref=payload.source_pref,
        note=payload.note,
    )
    db.add(plan)
    await db.flush()

    for it in payload.items:
        db.add(SalesPlanItem(
            plan_id=plan.id,
            product_id=uuid.UUID(it.product_id) if it.product_id else None,
            sku=it.sku,
            analysis_value=Decimal(str(it.analysis_value)),
            share_pct=Decimal(str(it.share_pct)),
            plan_value=Decimal(str(it.plan_value)),
        ))
    await db.commit()
    await db.refresh(plan)

    items = (await db.execute(
        select(SalesPlanItem).where(SalesPlanItem.plan_id == plan.id)
    )).scalars().all()
    return PlanDetail(
        **_plan_to_row(plan, len(items)).model_dump(),
        items=[_item_to_row(i, name=None) for i in items],
    )


@router.get("", response_model=list[PlanRow])
async def list_plans(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PlanRow]:
    plans = (await db.execute(
        select(SalesPlan).where(SalesPlan.company_id == current_user.company_id)
        .order_by(SalesPlan.period_start.desc())
    )).scalars().all()

    rows = []
    for p in plans:
        cnt = (await db.execute(
            select(SalesPlanItem).where(SalesPlanItem.plan_id == p.id)
        )).scalars().all()
        rows.append(_plan_to_row(p, len(cnt)))
    return rows


@router.get("/{plan_id}", response_model=PlanDetail)
async def get_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlanDetail:
    try:
        pid = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")
    plan = await _get_plan_owned(db, pid, current_user.company_id)
    items = (await db.execute(
        select(SalesPlanItem).where(SalesPlanItem.plan_id == plan.id)
    )).scalars().all()
    # Имена товаров
    name_map = {}
    pids = [i.product_id for i in items if i.product_id]
    if pids:
        from app.models import Product
        rows = (await db.execute(
            select(Product.id, Product.name).where(Product.id.in_(pids))
        )).all()
        name_map = {r.id: r.name for r in rows}
    return PlanDetail(
        **_plan_to_row(plan, len(items)).model_dump(),
        items=[_item_to_row(i, name=name_map.get(i.product_id)) for i in items],
    )


@router.patch("/{plan_id}", response_model=PlanRow)
async def update_plan(
    plan_id: str,
    payload: PlanUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlanRow:
    try:
        pid = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")
    plan = await _get_plan_owned(db, pid, current_user.company_id)
    if payload.name is not None:
        plan.name = payload.name
    if payload.target_value is not None:
        plan.target_value = Decimal(str(payload.target_value))
    if payload.distribution_mode is not None:
        plan.distribution_mode = payload.distribution_mode
    if payload.note is not None:
        plan.note = payload.note
    plan.updated_at = datetime.now(tz=plan.updated_at.tzinfo if plan.updated_at.tzinfo else None)
    await db.commit()
    return _plan_to_row(plan)


@router.delete("/{plan_id}")
async def delete_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        pid = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")
    plan = await _get_plan_owned(db, pid, current_user.company_id)
    await db.delete(plan)
    await db.commit()
    return {"ok": True}


@router.patch("/{plan_id}/items/{item_id}", response_model=PlanItemRow)
async def update_item(
    plan_id: str,
    item_id: str,
    payload: ItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlanItemRow:
    try:
        pid = uuid.UUID(plan_id)
        iid = uuid.UUID(item_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")
    await _get_plan_owned(db, pid, current_user.company_id)
    item = (await db.execute(
        select(SalesPlanItem).where(
            SalesPlanItem.id == iid, SalesPlanItem.plan_id == pid,
        )
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Позиция не найдена")
    if payload.plan_value is not None:
        item.plan_value = Decimal(str(payload.plan_value))
    if payload.is_locked is not None:
        item.is_locked = payload.is_locked
    await db.commit()
    return _item_to_row(item)


@router.post("/{plan_id}/rebalance", response_model=PlanDetail)
async def rebalance(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlanDetail:
    """Перераспределить НЕ-залоченные items так, чтобы сумма = target."""
    try:
        pid = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")
    plan = await _get_plan_owned(db, pid, current_user.company_id)
    items = (await db.execute(
        select(SalesPlanItem).where(SalesPlanItem.plan_id == pid)
    )).scalars().all()

    locked_sum = sum(float(i.plan_value) for i in items if i.is_locked)
    target = float(plan.target_value)
    remaining = max(0.0, target - locked_sum)
    unlocked_analysis = sum(float(i.analysis_value) for i in items if not i.is_locked)

    if unlocked_analysis > 0:
        for i in items:
            if i.is_locked:
                continue
            share = float(i.analysis_value) / unlocked_analysis
            i.plan_value = Decimal(str(round(remaining * share, 2)))
            i.share_pct = Decimal(str(round(share * 100, 4)))
    await db.commit()
    return await get_plan(plan_id=str(pid), current_user=current_user, db=db)


@router.post("/{plan_id}/distribute-days")
async def distribute_days(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Раскинуть plan_value каждого item по дням периода с сезонными весами."""
    try:
        pid = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")
    plan = await _get_plan_owned(db, pid, current_user.company_id)

    history = await fetch_history(
        db, company_id=current_user.company_id, metric=plan.metric_code,
        analysis_start=plan.analysis_start, analysis_end=plan.analysis_end,
    )
    fc = compute_forecast(
        history, plan.period_start, plan.period_end,
        target_value=float(plan.target_value),
    )

    items = (await db.execute(
        select(SalesPlanItem).where(SalesPlanItem.plan_id == pid)
    )).scalars().all()

    # Удаляем старые daily
    for it in items:
        await db.execute(
            delete(SalesPlanDaily).where(SalesPlanDaily.plan_item_id == it.id)
        )
    await db.flush()

    total_days = 0
    for it in items:
        for d_iso, weight in fc.season_weights.items():
            db.add(SalesPlanDaily(
                plan_item_id=it.id,
                date=date.fromisoformat(d_iso),
                plan_value=Decimal(str(round(float(it.plan_value) * weight, 2))),
                season_weight=Decimal(str(round(weight, 6))),
            ))
            total_days += 1
    await db.commit()
    return {"daily_rows": total_days, "reliability": fc.reliability}


# ============================================
# Simulate cascade
# ============================================

@router.post("/simulate")
async def simulate(
    payload: SimulateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """«+10000 кликов» → каскад с эффектами на orders/revenue/margin/ДРР."""
    cabinet = uuid.UUID(payload.cabinet_id) if payload.cabinet_id else None
    result = await simulate_plan_change(
        db, company_id=current_user.company_id, metric=payload.metric,
        delta=payload.delta, period_start=payload.period_start,
        period_end=payload.period_end, cabinet_id=cabinet,
    )
    return {
        "input_metric": result.input_metric,
        "input_delta": result.input_delta,
        "base_period": {
            "from": result.base_period[0].isoformat(),
            "to": result.base_period[1].isoformat(),
        },
        "effects": [
            {"metric": e.metric, "delta": e.delta,
             "new_value": e.new_value, "explanation": e.explanation}
            for e in result.effects
        ],
        "cpc_breakeven": result.cpc_breakeven,
        "drr_before_pct": result.drr_before_pct,
        "drr_after_pct": result.drr_after_pct,
        "note": result.note,
    }


# ============================================
# Fact + bridge
# ============================================

@router.get("/{plan_id}/fact")
async def get_fact(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        pid = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")
    plan = await _get_plan_owned(db, pid, current_user.company_id)
    cabinet = uuid.UUID(plan.scope_ref) if plan.scope_type == "cabinet" and plan.scope_ref else None
    result = await compute_fact(
        db, company_id=current_user.company_id,
        plan_value=float(plan.target_value), metric=plan.metric_code,
        period_start=plan.period_start, period_end=plan.period_end,
        cabinet_id=cabinet,
    )
    return {
        "plan_value": result.plan_value,
        "fact_value": result.fact_value,
        "fact_source": result.fact_source,
        "is_preliminary": result.is_preliminary,
        "delta_realization_tx": result.delta_realization_tx,
        "completion_pct": result.completion_pct,
        "completion_prorata_pct": result.completion_prorata_pct,
        "run_rate_forecast": result.run_rate_forecast,
        "needed_per_day": result.needed_per_day,
        "days_elapsed": result.days_elapsed,
        "days_remaining": result.days_remaining,
        "days_total": result.days_total,
        "probability_pct": result.probability_pct,
        "bridge": [
            {"name": b.name, "value": b.value, "explanation": b.explanation}
            for b in result.bridge
        ],
        "note": result.note,
    }


# ============================================
# KPI
# ============================================

@router.post("/{plan_id}/kpi")
async def create_kpi(
    plan_id: str,
    payload: KPICreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        pid = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")
    await _get_plan_owned(db, pid, current_user.company_id)
    kpi = PlanKPI(
        plan_id=pid, manager_name=payload.manager_name,
        metric_code=payload.metric_code,
        target_value=Decimal(str(payload.target_value)),
        bonus_rule=payload.bonus_rule,
    )
    db.add(kpi)
    await db.commit()
    return {
        "id": str(kpi.id), "manager_name": kpi.manager_name,
        "metric_code": kpi.metric_code, "target_value": float(kpi.target_value),
        "bonus_rule": kpi.bonus_rule,
    }


@router.get("/{plan_id}/kpi")
async def list_kpi(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        pid = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")
    await _get_plan_owned(db, pid, current_user.company_id)
    rows = (await db.execute(
        select(PlanKPI).where(PlanKPI.plan_id == pid).order_by(PlanKPI.created_at)
    )).scalars().all()
    return [
        {
            "id": str(k.id), "manager_name": k.manager_name,
            "metric_code": k.metric_code,
            "target_value": float(k.target_value),
            "bonus_rule": k.bonus_rule,
        }
        for k in rows
    ]
