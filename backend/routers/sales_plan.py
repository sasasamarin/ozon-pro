"""
/api/plan — планы продаж.

POST   /api/plan/sales                             — создать план
GET    /api/plan/sales                             — список планов
GET    /api/plan/sales/{plan_id}                   — один план
POST   /api/plan/sales/{plan_id}/items             — добавить SKU
PUT    /api/plan/sales/{plan_id}/items/{item_id}   — изменить позицию
POST   /api/plan/sales/{plan_id}/distribute        — распределить по дням
GET    /api/plan/sales/{plan_id}/fact              — факт vs план
POST   /api/plan/forecast                          — прогноз метрики
POST   /api/plan/simulate                          — каскадный пересчёт
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.sales_plan import (
    ChartPoint,
    FactVsPlanRow,
    ForecastRequest,
    ForecastResponse,
    ForecastSkuItem,
    PlanDailyOut,
    PlanItemCreate,
    PlanItemOut,
    PlanItemUpdate,
    SimulateRequest,
    SimulateResponse,
)
from app.services.forecast import forecast as run_forecast
from app.services.plan_cascade import simulate_plan_change
from schemas.sales_plan import SalesPlanCreate, SalesPlanDetail, SalesPlanRow

router = APIRouter()
UTC = timezone.utc

# Агрегации по метрике для JOIN-запроса transactions→orders→order_items
_SKU_AGG: dict[str, str] = {
    "revenue": "COALESCE(SUM(t.accruals_for_sale), 0)",
    "orders":  "COUNT(DISTINCT t.posting_number) FILTER (WHERE t.posting_number IS NOT NULL)",
    "units":   "COUNT(*)",
    "margin": (
        "COALESCE(SUM(t.accruals_for_sale), 0)"
        " + COALESCE(SUM(t.sale_commission), 0)"
        " + COALESCE(SUM(t.delivery_to_customer), 0)"
        " + COALESCE(SUM(t.return_logistics), 0)"
    ),
}


def _week_weights(daily_vals: list[float]) -> list[float]:
    """Суммирует дневные значения прогноза по неделям (группы по 7 дней)."""
    weeks = [
        round(sum(daily_vals[i:i + 7]), 4)
        for i in range(0, len(daily_vals), 7)
    ]
    return weeks or [1.0, 1.0, 1.0, 1.0]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _row_to_detail(row) -> SalesPlanDetail:
    return SalesPlanDetail(
        id=row.id,
        company_id=row.company_id,
        scope_type=row.scope_type,
        scope_ref=row.scope_ref,
        metric_code=row.metric_code,
        period_start=row.period_start,
        period_end=row.period_end,
        analysis_start=row.analysis_start,
        analysis_end=row.analysis_end,
        base_forecast=float(row.base_forecast) if row.base_forecast is not None else None,
        target_value=float(row.target_value) if row.target_value is not None else None,
        distribution_mode=row.distribution_mode,
        source_pref=row.source_pref,
        note=row.note,
        source=row.source,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _row_to_item(row) -> PlanItemOut:
    return PlanItemOut(
        id=row.id,
        plan_id=row.plan_id,
        sku=row.sku,
        glue_id=row.glue_id,
        analysis_value=float(row.analysis_value) if row.analysis_value is not None else None,
        share_pct=float(row.share_pct) if row.share_pct is not None else None,
        plan_value=float(row.plan_value) if row.plan_value is not None else None,
        is_locked=bool(row.is_locked),
    )


async def _get_plan(plan_id: int, db: AsyncSession):
    """Читает план по id. 404 если нет."""
    row = (await db.execute(
        text("SELECT * FROM sales_plan WHERE id = :id"),
        {"id": plan_id},
    )).mappings().one_or_none()
    if not row:
        raise HTTPException(404, "План не найден")
    return row


async def _recalc_shares(plan_id: int, db: AsyncSession) -> None:
    """Пересчитывает share_pct для всех позиций плана."""
    await db.execute(text("""
        UPDATE sales_plan_item i
        SET share_pct = CASE
            WHEN totals.total_plan > 0
            THEN i.plan_value / totals.total_plan * 100
            ELSE NULL
        END
        FROM (
            SELECT SUM(plan_value) AS total_plan
            FROM sales_plan_item
            WHERE plan_id = :plan_id
        ) AS totals
        WHERE i.plan_id = :plan_id
    """), {"plan_id": plan_id})


async def _analysis_value_for_sku(
    plan,
    sku: str,
    db: AsyncSession,
) -> Optional[float]:
    """Исторический объём по метрике плана для конкретного SKU за analysis-период."""
    analysis_start = plan["analysis_start"] or plan["period_start"]
    analysis_end = plan["analysis_end"] or plan["period_end"]

    metric = plan["metric_code"]
    if metric == "orders":
        agg = "COUNT(DISTINCT t.posting_number) FILTER (WHERE t.posting_number IS NOT NULL)"
    else:
        agg = "COALESCE(SUM(t.accruals_for_sale), 0)"

    row = (await db.execute(text(f"""
        SELECT {agg} AS val
        FROM transactions t
        JOIN orders o ON o.posting_number = t.posting_number
                      AND o.ozon_account_id = t.ozon_account_id
        JOIN order_items oi ON oi.order_id = o.id
        WHERE t.time >= :ts_from
          AND t.time <  :ts_to + INTERVAL '1 day'
          AND oi.offer_id = :sku
    """), {
        "ts_from": analysis_start,
        "ts_to": analysis_end,
        "sku": sku,
    })).mappings().one_or_none()

    if row and row["val"] is not None:
        return float(row["val"])
    return None


# ── Планы: базовые CRUD ───────────────────────────────────────────────────────

@router.post("/sales", response_model=SalesPlanDetail, status_code=201)
async def create_plan(
    payload: SalesPlanCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SalesPlanDetail:
    row = (await db.execute(
        text("""
            INSERT INTO sales_plan (
                company_id, scope_type, scope_ref, metric_code,
                period_start, period_end, target_value,
                distribution_mode, source_pref, note, source
            ) VALUES (
                :company_id, :scope_type, :scope_ref, :metric_code,
                :period_start, :period_end, :target_value,
                'proportional', :source_pref, :note, 'user'
            )
            RETURNING *
        """),
        {
            "company_id": payload.company_id,
            "scope_type": payload.scope_type,
            "scope_ref": payload.scope_ref,
            "metric_code": payload.metric_code,
            "period_start": payload.period_start,
            "period_end": payload.period_end,
            "target_value": payload.target_value,
            "source_pref": payload.source_pref,
            "note": payload.note,
        },
    )).mappings().one()
    await db.commit()
    return _row_to_detail(row)


@router.get("/sales", response_model=list[SalesPlanRow])
async def list_plans(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SalesPlanRow]:
    filters = "WHERE company_id = :company_id"
    params: dict = {"company_id": current_user.company_id}
    if period_start:
        filters += " AND period_end >= :period_start"
        params["period_start"] = period_start
    if period_end:
        filters += " AND period_start <= :period_end"
        params["period_end"] = period_end

    rows = (await db.execute(
        text(f"""
            SELECT id, scope_type, scope_ref, metric_code, target_value,
                   period_start, period_end
            FROM sales_plan
            {filters}
            ORDER BY period_start DESC, id DESC
        """),
        params,
    )).mappings().all()

    return [
        SalesPlanRow(
            id=r.id,
            scope_type=r.scope_type,
            scope_ref=r.scope_ref,
            metric_code=r.metric_code,
            target_value=float(r.target_value) if r.target_value is not None else None,
            period_start=r.period_start,
            period_end=r.period_end,
        )
        for r in rows
    ]


@router.get("/sales/{plan_id}", response_model=SalesPlanDetail)
async def get_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SalesPlanDetail:
    plan = await _get_plan(plan_id, db)
    return _row_to_detail(plan)


# ── Позиции плана ─────────────────────────────────────────────────────────────

@router.post("/sales/{plan_id}/items", response_model=PlanItemOut, status_code=201)
async def add_plan_item(
    plan_id: int,
    payload: PlanItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlanItemOut:
    plan = await _get_plan(plan_id, db)

    analysis_val = await _analysis_value_for_sku(plan, payload.sku, db)

    row = (await db.execute(text("""
        INSERT INTO sales_plan_item
            (plan_id, sku, analysis_value, plan_value, is_locked)
        VALUES (:plan_id, :sku, :analysis_value, :plan_value, :is_locked)
        RETURNING *
    """), {
        "plan_id": plan_id,
        "sku": payload.sku,
        "analysis_value": analysis_val,
        "plan_value": payload.plan_value,
        "is_locked": payload.is_locked,
    })).mappings().one()

    await _recalc_shares(plan_id, db)
    await db.commit()

    # Перечитываем с обновлённым share_pct
    refreshed = (await db.execute(
        text("SELECT * FROM sales_plan_item WHERE id = :id"),
        {"id": row.id},
    )).mappings().one()
    return _row_to_item(refreshed)


@router.put("/sales/{plan_id}/items/{item_id}", response_model=PlanItemOut)
async def update_plan_item(
    plan_id: int,
    item_id: int,
    payload: PlanItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlanItemOut:
    await _get_plan(plan_id, db)

    item = (await db.execute(
        text("SELECT * FROM sales_plan_item WHERE id = :id AND plan_id = :plan_id"),
        {"id": item_id, "plan_id": plan_id},
    )).mappings().one_or_none()
    if not item:
        raise HTTPException(404, "Позиция не найдена")

    # Частичное обновление
    updates: dict = {}
    if payload.plan_value is not None:
        updates["plan_value"] = payload.plan_value
    if payload.is_locked is not None:
        updates["is_locked"] = payload.is_locked

    if updates:
        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        updates["id"] = item_id
        await db.execute(
            text(f"UPDATE sales_plan_item SET {set_clause} WHERE id = :id"),
            updates,
        )

    # Пересчитываем share_pct незалоченных если item был разлочен
    if payload.is_locked is False or payload.plan_value is not None:
        await _recalc_shares(plan_id, db)

    await db.commit()

    refreshed = (await db.execute(
        text("SELECT * FROM sales_plan_item WHERE id = :id"),
        {"id": item_id},
    )).mappings().one()
    return _row_to_item(refreshed)


# ── Распределение по дням ─────────────────────────────────────────────────────

@router.post("/sales/{plan_id}/distribute", response_model=list[PlanDailyOut])
async def distribute_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PlanDailyOut]:
    plan = await _get_plan(plan_id, db)
    period_start: date = plan["period_start"]
    period_end: date = plan["period_end"]
    analysis_start: date = plan["analysis_start"] or period_start
    analysis_end: date = plan["analysis_end"] or period_end

    # Прошлогодний аналог: сдвигаем analysis на −1 год
    ly_start = date(analysis_start.year - 1, analysis_start.month, analysis_start.day)
    ly_end = date(analysis_end.year - 1, analysis_end.month, analysis_end.day)

    # Суточная выручка за прошлогодний период → сезонные веса по дням недели
    hist_rows = (await db.execute(text("""
        SELECT
            DATE(time AT TIME ZONE 'Europe/Moscow') AS day,
            COALESCE(SUM(accruals_for_sale), 0)    AS revenue
        FROM transactions
        WHERE time >= :from_dt
          AND time <  :to_dt + INTERVAL '1 day'
        GROUP BY 1
        ORDER BY 1
    """), {"from_dt": ly_start, "to_dt": ly_end})).mappings().all()

    # Строим словарь dow → средняя выручка
    dow_sums: dict[int, float] = {}
    dow_counts: dict[int, int] = {}
    for r in hist_rows:
        dow = r["day"].weekday()
        v = float(r["revenue"])
        dow_sums[dow] = dow_sums.get(dow, 0.0) + v
        dow_counts[dow] = dow_counts.get(dow, 0) + 1

    dow_avg = {
        dow: dow_sums[dow] / dow_counts[dow]
        for dow in dow_sums
    }

    n_days = (period_end - period_start).days + 1
    plan_dates = [period_start + timedelta(days=i) for i in range(n_days)]

    # Нормализованные веса по периоду плана (Σ = 1)
    raw_weights = [dow_avg.get(d.weekday(), 1.0) for d in plan_dates]
    total_raw = sum(raw_weights) or n_days
    season_weights = [w / total_raw for w in raw_weights]

    # Позиции плана
    items = (await db.execute(
        text("SELECT * FROM sales_plan_item WHERE plan_id = :plan_id"),
        {"plan_id": plan_id},
    )).mappings().all()

    created: list[PlanDailyOut] = []
    for item in items:
        item_plan = float(item["plan_value"] or 0)
        # Удаляем старое распределение перед перезаписью
        await db.execute(
            text("DELETE FROM sales_plan_daily WHERE plan_item_id = :item_id"),
            {"item_id": item["id"]},
        )
        for d, sw in zip(plan_dates, season_weights):
            day_val = round(item_plan * sw, 2)
            row = (await db.execute(text("""
                INSERT INTO sales_plan_daily
                    (plan_item_id, date, plan_value, season_weight)
                VALUES (:item_id, :date, :plan_value, :season_weight)
                RETURNING *
            """), {
                "item_id": item["id"],
                "date": d,
                "plan_value": day_val,
                "season_weight": round(sw, 6),
            })).mappings().one()
            created.append(PlanDailyOut(
                id=row.id,
                plan_item_id=row.plan_item_id,
                date=row.date,
                plan_value=float(row.plan_value) if row.plan_value is not None else None,
                season_weight=float(row.season_weight) if row.season_weight is not None else None,
            ))

    await db.commit()
    return created


# ── Факт vs план ─────────────────────────────────────────────────────────────

@router.get("/sales/{plan_id}/fact", response_model=FactVsPlanRow)
async def plan_fact(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FactVsPlanRow:
    plan = await _get_plan(plan_id, db)
    period_start: date = plan["period_start"]
    period_end: date = plan["period_end"]
    metric: str = plan["metric_code"]
    target: Optional[float] = float(plan["target_value"]) if plan["target_value"] else None

    today = datetime.now(UTC).date()
    is_closed = period_end < today

    # Агрегат транзакций за период плана (MTD или полный если закрыт)
    fact_end = period_end if is_closed else min(today, period_end)

    if metric == "orders":
        agg_expr = "COUNT(DISTINCT posting_number) FILTER (WHERE posting_number IS NOT NULL)"
    else:
        agg_expr = "COALESCE(SUM(accruals_for_sale), 0)"

    tx_row = (await db.execute(text(f"""
        SELECT {agg_expr} AS val
        FROM transactions
        WHERE time >= :ts_from
          AND time <  :ts_to + INTERVAL '1 day'
    """), {
        "ts_from": period_start,
        "ts_to": fact_end,
    })).mappings().one()
    fact_tx = float(tx_row["val"] or 0)

    # Если период закрыт — пробуем realization_daily (официальные данные Ozon)
    source = "operational"
    fact = fact_tx
    delta_real_str: Optional[str] = None

    if is_closed:
        real_row = (await db.execute(text("""
            SELECT COALESCE(SUM(qty_sold * weighted_sp), 0) AS val
            FROM realization_daily
            WHERE day >= :from_dt
              AND day <= :to_dt
        """), {
            "from_dt": period_start,
            "to_dt": period_end,
        })).mappings().one_or_none()

        if real_row and real_row["val"]:
            fact_real = float(real_row["val"])
            delta_real = fact_real - fact_tx
            delta_real_str = f"{'+' if delta_real >= 0 else ''}{delta_real:,.2f} ₽"
            fact = fact_real
            source = "official"

    # Расчёт показателей
    total_days = (period_end - period_start).days + 1
    days_passed = max(1, min(total_days, (today - period_start).days + 1))
    days_remaining = max(0, total_days - days_passed)

    pro_rata = round(target * days_passed / total_days, 2) if target else None
    plan_pct = round(fact / target * 100, 1) if target and target > 0 else None
    run_rate = round(fact / days_passed * total_days, 2) if days_passed > 0 else None
    needed = round((target - fact) / days_remaining, 2) if target and days_remaining > 0 else None

    return FactVsPlanRow(
        metric=metric,
        plan=target,
        fact=round(fact, 2),
        plan_pct=plan_pct,
        pro_rata=pro_rata,
        run_rate=run_rate,
        needed_per_day=needed,
        source=source,
        delta_realization=delta_real_str,
    )


# ── Прогноз ──────────────────────────────────────────────────────────────────

@router.post("/forecast", response_model=ForecastResponse)
async def forecast_endpoint(
    payload: ForecastRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ForecastResponse:
    cabinet_id_str = payload.cabinet_id
    if cabinet_id_str is None:
        rows = (await db.execute(
            text(
                "SELECT id FROM ozon_accounts"
                " WHERE company_id = :cid AND deleted_at IS NULL"
                " ORDER BY id"
            ),
            {"cid": current_user.company_id},
        )).all()
        if not rows:
            raise HTTPException(400, "Нет доступных кабинетов для компании")
        cabinet_id_str = str(rows[0][0])

    cabinet_uuid = uuid.UUID(cabinet_id_str)

    result = await run_forecast(
        metric=payload.metric_code,
        analysis_start=payload.analysis_start,
        analysis_end=payload.analysis_end,
        forecast_start=payload.forecast_start,
        forecast_end=payload.forecast_end,
        cabinet_id=cabinet_uuid,
        db=db,
        skus=payload.skus if payload.skus else None,
    )

    # Разделяем history и forecast_series по границе None-значений
    n_analysis = sum(1 for v in result.history if v is not None)
    history_chart = [
        ChartPoint(date=result.dates[i], value=result.history[i])  # type: ignore[arg-type]
        for i in range(n_analysis)
    ]
    forecast_chart = [
        ChartPoint(date=result.dates[i], value=result.base_forecast[i])
        for i in range(n_analysis, len(result.dates))
    ]

    # Недельные веса из дневного прогноза (для Step 3 фронта)
    sw = _week_weights(result.base_forecast[n_analysis:])

    # Факт по SKU за период анализа через JOIN transactions→orders→order_items
    agg_expr = _SKU_AGG.get(payload.metric_code, _SKU_AGG["revenue"])
    sku_rows = (await db.execute(text(f"""
        SELECT
            oi.offer_id,
            MAX(oi.name) AS name,
            {agg_expr} AS fact_value
        FROM transactions t
        JOIN orders o ON o.posting_number = t.posting_number
                     AND o.ozon_account_id = t.ozon_account_id
        JOIN order_items oi ON oi.order_id = o.id
        WHERE t.ozon_account_id = :cabinet_id
          AND t.time >= :date_from
          AND t.time < CAST(:date_to AS timestamp) + INTERVAL '1 day'
          AND oi.offer_id IS NOT NULL
        GROUP BY oi.offer_id
        ORDER BY fact_value DESC
    """), {
        "cabinet_id": cabinet_uuid,
        "date_from": payload.analysis_start,
        "date_to": payload.analysis_end,
    })).mappings().all()

    total_fact = sum(float(r["fact_value"] or 0) for r in sku_rows) or 1.0

    items = [
        ForecastSkuItem(
            sku_id=r["offer_id"],
            offer_id=r["offer_id"],
            name=r["name"] or r["offer_id"],
            cabinet_id=cabinet_id_str,
            fact=round(float(r["fact_value"] or 0), 2),
            forecast=round(result.total_forecast * float(r["fact_value"] or 0) / total_fact, 2),
            season_weights=sw,
            reliability=result.badge,
        )
        for r in sku_rows
    ]

    return ForecastResponse(
        items=items,
        history=history_chart,
        forecast_series=forecast_chart,
    )


# ── Каскадный симулятор ───────────────────────────────────────────────────────

@router.post("/simulate", response_model=SimulateResponse)
async def simulate_endpoint(
    payload: SimulateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SimulateResponse:
    result = await simulate_plan_change(
        plan_id=payload.plan_id,
        metric=payload.metric,
        delta=payload.delta,
        db=db,
    )
    if "error" in result:
        raise HTTPException(404, result["error"])

    return SimulateResponse(
        plan_id=result["plan_id"],
        metric=result["metric"],
        delta=result["delta"],
        cascade=result["cascade"],
        sources=result["sources"],
    )
