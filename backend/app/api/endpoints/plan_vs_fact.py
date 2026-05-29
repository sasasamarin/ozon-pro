"""
/analytics/plan-vs-fact: цели + факт + прогноз дотягивания.

GET    /api/v1/analytics/plan-vs-fact?period_from=YYYY-MM-DD&period_to=YYYY-MM-DD
POST   /api/v1/analytics/plan-vs-fact/targets   — создать/обновить цель
DELETE /api/v1/analytics/plan-vs-fact/targets/{id}
GET    /api/v1/analytics/plan-vs-fact/targets   — список целей за период
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Order, OrderItem, OzonAccount, Product, Transaction, User
from app.models.kpi import KPITarget

router = APIRouter()
UTC = timezone.utc


class TargetRow(BaseModel):
    id: str
    period_from: str
    period_to: str
    metric: str
    target_value: float
    cabinet_id: str | None
    notes: str | None


class TargetCreate(BaseModel):
    period_from: date_cls
    period_to: date_cls
    metric: str = Field(description="revenue|gross_profit|orders|aov|margin_pct")
    target_value: float = Field(gt=0)
    cabinet_id: str | None = None
    notes: str | None = None


class PVFRow(BaseModel):
    metric: str
    label: str
    target: float
    fact: float
    progress_pct: float
    forecast: float           # прогноз на конец периода исходя из текущей скорости
    forecast_progress_pct: float
    days_passed: int
    days_remaining: int


class PVFResponse(BaseModel):
    period_from: str
    period_to: str
    rows: list[PVFRow]


METRICS_INFO = {
    "revenue": {"label": "Выручка ₽", "unit": "money"},
    "gross_profit": {"label": "Валовая прибыль ₽", "unit": "money"},
    "orders": {"label": "Заказы (шт)", "unit": "count"},
    "aov": {"label": "Средний чек ₽", "unit": "money"},
    "margin_pct": {"label": "Маржа %", "unit": "pct"},
}


_EXPENSE_FIELDS = (
    "sale_commission", "delivery_to_customer", "return_logistics", "last_mile",
    "storage", "placement", "acquiring", "advertising", "utilization",
)


async def _fact_for_metric(
    db: AsyncSession, *, accs: list[uuid.UUID], metric: str,
    dt_from: datetime, dt_to: datetime,
) -> float:
    if not accs:
        return 0.0
    rev_row = (await db.execute(
        select(
            func.coalesce(func.sum(Order.total_amount), 0),
            func.count(Order.id),
        ).where(
            Order.ozon_account_id.in_(accs),
            Order.order_created_at >= dt_from,
            Order.order_created_at < dt_to,
            Order.status == "delivered",
        )
    )).one()
    revenue = float(rev_row[0] or 0)
    orders = int(rev_row[1] or 0)

    if metric == "revenue":
        return revenue
    if metric == "orders":
        return float(orders)
    if metric == "aov":
        return revenue / orders if orders > 0 else 0

    # COGS + expenses нужны для gross_profit / margin_pct
    cogs_row = await db.execute(
        select(
            func.coalesce(
                func.sum(OrderItem.quantity * func.coalesce(Product.cost_price, 0)), 0
            )
        )
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            Order.ozon_account_id.in_(accs),
            Order.order_created_at >= dt_from,
            Order.order_created_at < dt_to,
            Order.status == "delivered",
        )
    )
    cogs = float(cogs_row.scalar() or 0)
    exp_cols = [
        func.coalesce(func.sum(func.abs(getattr(Transaction, f))), 0)
        for f in _EXPENSE_FIELDS
    ]
    exp_row = (await db.execute(
        select(*exp_cols).where(
            Transaction.ozon_account_id.in_(accs),
            Transaction.time >= dt_from,
            Transaction.time < dt_to,
        )
    )).one()
    ozon_expenses = sum(float(v or 0) for v in exp_row)
    gross = revenue - cogs - ozon_expenses
    if metric == "gross_profit":
        return gross
    if metric == "margin_pct":
        return (gross / revenue * 100) if revenue > 0 else 0
    return 0


async def _account_ids(
    db: AsyncSession, *, company_id: uuid.UUID, cabinet_ids: list[uuid.UUID] | None
) -> list[uuid.UUID]:
    q = select(OzonAccount.id).where(
        OzonAccount.company_id == company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if cabinet_ids:
        q = q.where(OzonAccount.id.in_(cabinet_ids))
    return [r[0] for r in (await db.execute(q)).all()]


@router.get("/", response_model=PVFResponse)
async def get_pvf(
    period_from: date_cls | None = Query(None),
    period_to: date_cls | None = Query(None),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PVFResponse:
    today = datetime.now(UTC).date()
    if not period_from or not period_to:
        # дефолт — текущий месяц
        period_from = today.replace(day=1)
        next_m = (period_from + timedelta(days=32)).replace(day=1)
        period_to = next_m - timedelta(days=1)

    accs = await _account_ids(db, company_id=current_user.company_id, cabinet_ids=cabinet_ids)

    # Цели за период
    targets = (await db.execute(
        select(KPITarget).where(
            KPITarget.company_id == current_user.company_id,
            KPITarget.period_from <= period_to,
            KPITarget.period_to >= period_from,
        )
    )).scalars().all()

    # group by metric — последнее значение
    target_by_metric: dict[str, float] = {}
    for t in targets:
        target_by_metric[t.metric] = float(t.target_value)

    # Если целей нет — возвращаем пустой список
    if not target_by_metric:
        return PVFResponse(
            period_from=period_from.isoformat(),
            period_to=period_to.isoformat(),
            rows=[],
        )

    total_days = (period_to - period_from).days + 1
    days_passed = max(0, min(total_days, (today - period_from).days + 1))
    days_remaining = max(0, total_days - days_passed)

    # Фактические окна
    dt_from = datetime.combine(period_from, datetime.min.time(), tzinfo=UTC)
    fact_to = today + timedelta(days=1) if today < period_to else period_to + timedelta(days=1)
    dt_to_fact = datetime.combine(fact_to, datetime.min.time(), tzinfo=UTC)

    rows: list[PVFRow] = []
    for metric, target in target_by_metric.items():
        fact = await _fact_for_metric(db, accs=accs, metric=metric, dt_from=dt_from, dt_to=dt_to_fact)
        progress = (fact / target * 100) if target > 0 else 0
        # прогноз: текущий темп × total дней
        if days_passed > 0 and metric not in ("aov", "margin_pct"):
            forecast = fact / days_passed * total_days
        else:
            forecast = fact
        forecast_progress = (forecast / target * 100) if target > 0 else 0
        rows.append(PVFRow(
            metric=metric,
            label=METRICS_INFO.get(metric, {}).get("label", metric),
            target=round(target, 2),
            fact=round(fact, 2),
            progress_pct=round(progress, 1),
            forecast=round(forecast, 2),
            forecast_progress_pct=round(forecast_progress, 1),
            days_passed=days_passed,
            days_remaining=days_remaining,
        ))

    return PVFResponse(
        period_from=period_from.isoformat(),
        period_to=period_to.isoformat(),
        rows=rows,
    )


@router.get("/targets", response_model=list[TargetRow])
async def list_targets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TargetRow]:
    rows = (await db.execute(
        select(KPITarget).where(KPITarget.company_id == current_user.company_id)
        .order_by(desc(KPITarget.period_from))
    )).scalars().all()
    return [
        TargetRow(
            id=str(t.id),
            period_from=t.period_from.isoformat(),
            period_to=t.period_to.isoformat(),
            metric=t.metric,
            target_value=float(t.target_value),
            cabinet_id=str(t.cabinet_id) if t.cabinet_id else None,
            notes=t.notes,
        ) for t in rows
    ]


@router.post("/targets", response_model=TargetRow)
async def create_target(
    payload: TargetCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TargetRow:
    if payload.metric not in METRICS_INFO:
        raise HTTPException(400, f"Невалидная метрика: {payload.metric}")
    if payload.period_to < payload.period_from:
        raise HTTPException(400, "period_to < period_from")

    cab_id: uuid.UUID | None = None
    if payload.cabinet_id:
        try:
            cab_id = uuid.UUID(payload.cabinet_id)
        except ValueError:
            raise HTTPException(400, "Невалидный cabinet_id")

    # Upsert
    existing = (await db.execute(
        select(KPITarget).where(
            KPITarget.company_id == current_user.company_id,
            KPITarget.period_from == payload.period_from,
            KPITarget.period_to == payload.period_to,
            KPITarget.metric == payload.metric,
            KPITarget.cabinet_id == cab_id,
        )
    )).scalar_one_or_none()
    if existing:
        existing.target_value = payload.target_value
        existing.notes = payload.notes
        t = existing
    else:
        t = KPITarget(
            company_id=current_user.company_id,
            user_id=current_user.id,
            period_from=payload.period_from,
            period_to=payload.period_to,
            metric=payload.metric,
            target_value=payload.target_value,
            cabinet_id=cab_id,
            notes=payload.notes,
        )
        db.add(t)
    await db.commit()
    await db.refresh(t)

    return TargetRow(
        id=str(t.id),
        period_from=t.period_from.isoformat(),
        period_to=t.period_to.isoformat(),
        metric=t.metric,
        target_value=float(t.target_value),
        cabinet_id=str(t.cabinet_id) if t.cabinet_id else None,
        notes=t.notes,
    )


@router.delete("/targets/{target_id}")
async def delete_target(
    target_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        tid = uuid.UUID(target_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")
    t = (await db.execute(
        select(KPITarget).where(
            KPITarget.id == tid, KPITarget.company_id == current_user.company_id,
        )
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Не найдено")
    await db.delete(t)
    await db.commit()
    return {"deleted": True}
