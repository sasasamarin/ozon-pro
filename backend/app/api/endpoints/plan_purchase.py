"""
/analytics/plan-purchase — обратный расчёт «цель → закупка → факт».

Пошагово:
  1) Юзер задаёт цель: «продать X шт» или «получить Y ₽ прибыли» за период.
  2) Система берёт текущие метрики (velocity, средний чек, маржа, ДРР).
  3) Считает 3 сценария:
     A) Текущая цена + маржа: сколько фактически выйдет?
     B) Цена +N%: цель ближе, риск падения конверсии.
     C) Реклама +N% бюджета: больше показов и velocity.
  4) План закупки: разбивка на партии (lead_time + safety_stock) и кластеры.
  5) Факт vs план — endpoint /progress: фактические продажи за период
     vs цель, прогноз достижения, корректировка темпа.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import AnalyticsDaily, OzonAccount, Product, Transaction, User

router = APIRouter()
UTC = timezone.utc


class PurchasePlanInput(BaseModel):
    goal_type: Literal["units", "profit", "revenue"]
    goal_value: float
    period_days: int = 90        # за сколько хочешь достичь
    product_id: str | None = None  # если указан — расчёт per-SKU, иначе агрегат
    lead_time_days: int = 14
    safety_stock_days: int = 7
    baseline_window_days: int = 28  # сколько дней назад смотреть для baseline


class ScenarioResult(BaseModel):
    name: str                # "A: текущие цена и реклама" и т.д.
    description: str
    units_needed: int        # сколько шт нужно продать чтобы достичь цели
    revenue: float
    gross_profit: float
    avg_price: float         # цена за единицу в этом сценарии
    margin_pct: float        # маржа % в этом сценарии
    velocity_required: float # шт/день нужно
    velocity_today: float    # текущая скорость
    velocity_gap_pct: float  # на сколько % надо ускориться
    reachable: bool          # реально ли достичь цели?
    advice: str              # человеческий совет


class PurchaseBatch(BaseModel):
    month_index: int         # 0 = первый месяц
    month_label: str
    units_to_order: int
    reasoning: str


class PurchasePlan(BaseModel):
    total_units: int
    avg_batch_units: int
    batches: list[PurchaseBatch]
    reorder_point_units: int  # точка перезаказа = velocity × (lead+safety)


class PurchasePlanResp(BaseModel):
    period_from: str
    period_to: str
    product_id: str | None
    product_name: str | None
    baseline: dict           # «факты» которые легли в расчёт
    scenarios: list[ScenarioResult]
    purchase_plan: PurchasePlan
    note: str


def _safe(v, default=0.0):
    try: return float(v) if v is not None else default
    except (TypeError, ValueError): return default


@router.post("/calculate", response_model=PurchasePlanResp)
async def calculate_purchase_plan(
    payload: PurchasePlanInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PurchasePlanResp:
    today = datetime.now(UTC).date()
    horizon_to = today + timedelta(days=payload.period_days)
    base_from = today - timedelta(days=payload.baseline_window_days)

    # === account scope
    accs = [r[0] for r in (await db.execute(
        select(OzonAccount.id).where(
            OzonAccount.company_id == current_user.company_id,
            OzonAccount.deleted_at.is_(None),
        )
    )).all()]
    if not accs:
        raise HTTPException(400, "Нет подключённых кабинетов")

    pid: uuid.UUID | None = None
    prod_name: str | None = None
    cost_price = None
    if payload.product_id:
        try:
            pid = uuid.UUID(payload.product_id)
            prod = (await db.execute(select(Product).where(Product.id == pid))).scalar_one_or_none()
            if prod:
                prod_name = prod.name
                cost_price = _safe(prod.cost_price)
        except ValueError:
            pid = None

    # === Baseline за окно (28 дней по умолчанию)
    where = [
        Product.ozon_account_id.in_(accs),
        AnalyticsDaily.date >= base_from,
        AnalyticsDaily.date <= today,
    ]
    if pid:
        where.append(AnalyticsDaily.product_id == pid)

    base_row = (await db.execute(
        select(
            func.coalesce(func.sum(AnalyticsDaily.ordered_units), 0).label("units"),
            func.coalesce(func.sum(AnalyticsDaily.revenue), 0).label("revenue"),
            func.coalesce(func.count(func.distinct(AnalyticsDaily.date)), 1).label("days"),
        ).select_from(AnalyticsDaily)
        .join(Product, Product.id == AnalyticsDaily.product_id)
        .where(*where)
    )).one()
    units = int(base_row.units or 0)
    revenue = _safe(base_row.revenue)
    days_in_base = max(1, int(base_row.days or 1))
    avg_price = (revenue / units) if units > 0 else 0.0
    velocity_today = units / days_in_base   # шт/день

    # === ДРР сейчас (для сценария "С: больше рекламы")
    dt_from = datetime.combine(base_from, datetime.min.time(), tzinfo=UTC)
    dt_to = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    AD_OP_KEYS = [
        "OperationMarketplaceCostPerClick", "OperationPromotionWithCostPerOrder",
        "OperationElectronicServicesPromotionInS", "OperationGettingToTheTop",
        "OperationElectronicServiceStencil", "OperationMarketPlaceItemPinReview",
        "OperationLabelOriginal", "MarketplaceMarketingActionCostOperation",
        "OperationOtherElectronicServices",
    ]
    ad_spend = _safe((await db.execute(
        select(func.coalesce(func.sum(func.abs(Transaction.amount)), 0)).where(
            Transaction.ozon_account_id.in_(accs),
            Transaction.time >= dt_from,
            Transaction.time < dt_to,
            Transaction.operation_type.in_(AD_OP_KEYS),
        )
    )).scalar_one_or_none())
    drr_pct = (ad_spend / revenue * 100) if revenue else 0.0

    # === маржа: если cost_price известна и > 0 — точно; иначе приближение 30%
    if cost_price and cost_price > 0 and avg_price > 0:
        margin_pct = (avg_price - cost_price) / avg_price * 100
    else:
        margin_pct = 30.0  # дефолт
        cost_price = avg_price * (1 - margin_pct / 100) if avg_price else 0
    gross_profit_per_unit = avg_price - (cost_price or 0)

    # === Цель → units_needed (базовый сценарий A)
    def _units_for(goal_type: str, goal_value: float, gross_per_unit: float, price: float) -> int:
        if goal_type == "units":
            return int(round(goal_value))
        if goal_type == "revenue":
            return int(round(goal_value / price)) if price > 0 else 0
        if goal_type == "profit":
            return int(round(goal_value / gross_per_unit)) if gross_per_unit > 0 else 0
        return 0

    period_days = payload.period_days

    # === Сценарий A: текущая цена + текущая реклама
    units_A = _units_for(payload.goal_type, payload.goal_value, gross_profit_per_unit, avg_price)
    rev_A = units_A * avg_price
    profit_A = units_A * gross_profit_per_unit
    vel_req_A = units_A / period_days if period_days else 0
    gap_A = ((vel_req_A - velocity_today) / velocity_today * 100) if velocity_today else 0
    reachable_A = vel_req_A <= velocity_today * 1.15  # лёгкий буфер
    scenario_A = ScenarioResult(
        name="A: текущие цена и реклама",
        description=f"Цена {avg_price:.0f}₽, ДРР {drr_pct:.1f}%, маржа {margin_pct:.1f}%",
        units_needed=units_A, revenue=round(rev_A, 2), gross_profit=round(profit_A, 2),
        avg_price=round(avg_price, 2), margin_pct=round(margin_pct, 1),
        velocity_required=round(vel_req_A, 2), velocity_today=round(velocity_today, 2),
        velocity_gap_pct=round(gap_A, 1), reachable=reachable_A,
        advice=("По плану — продолжай в том же темпе." if reachable_A
                else f"Нужно ускориться на {gap_A:.0f}% — поднимай рекламу или меняй цену."),
    )

    # === Сценарий B: цена +10% (маржа выше, но конверсия может упасть на ~20%)
    new_price_B = avg_price * 1.10
    new_gross_B = new_price_B - (cost_price or 0)
    new_margin_pct_B = (new_gross_B / new_price_B * 100) if new_price_B else 0
    units_B = _units_for(payload.goal_type, payload.goal_value, new_gross_B, new_price_B)
    expected_vel_B = velocity_today * 0.80   # эмпирика: +10% цена → −20% conversion
    vel_req_B = units_B / period_days if period_days else 0
    gap_B = ((vel_req_B - expected_vel_B) / expected_vel_B * 100) if expected_vel_B else 0
    scenario_B = ScenarioResult(
        name="B: цена +10%",
        description=f"Цена {new_price_B:.0f}₽ (+10%), маржа {new_margin_pct_B:.1f}%, ожидаемая скорость −20%",
        units_needed=units_B, revenue=round(units_B * new_price_B, 2),
        gross_profit=round(units_B * new_gross_B, 2),
        avg_price=round(new_price_B, 2), margin_pct=round(new_margin_pct_B, 1),
        velocity_required=round(vel_req_B, 2), velocity_today=round(expected_vel_B, 2),
        velocity_gap_pct=round(gap_B, 1),
        reachable=vel_req_B <= expected_vel_B * 1.10,
        advice=("Меньше штук → меньше реклама и логистика."
                if units_B < units_A else "Цена выше, но конверсия упадёт — проверь эластичность."),
    )

    # === Сценарий C: реклама +50% бюджета (velocity +25%, ДРР +5п.п.)
    expected_vel_C = velocity_today * 1.25
    units_C = units_A
    vel_req_C = units_C / period_days if period_days else 0
    gap_C = ((vel_req_C - expected_vel_C) / expected_vel_C * 100) if expected_vel_C else 0
    new_drr_C = drr_pct + 5
    scenario_C = ScenarioResult(
        name="C: реклама +50% бюджета",
        description=f"Цена {avg_price:.0f}₽, ДРР {new_drr_C:.1f}% (+5 п.п.), ожидаемая скорость +25%",
        units_needed=units_C, revenue=round(units_C * avg_price, 2),
        gross_profit=round(units_C * gross_profit_per_unit - units_C * avg_price * 0.05, 2),
        avg_price=round(avg_price, 2), margin_pct=round(margin_pct, 1),
        velocity_required=round(vel_req_C, 2), velocity_today=round(expected_vel_C, 2),
        velocity_gap_pct=round(gap_C, 1),
        reachable=vel_req_C <= expected_vel_C * 1.10,
        advice="Больше штук, но прибыль — минус доп. реклама. Подходит для быстрого роста.",
    )

    # === План закупки (на основе сценария A — оптимального по риску)
    total_units = max(1, units_A)
    # помесячно
    months = max(1, period_days // 30)
    per_month = round(total_units / months)
    batches: list[PurchaseBatch] = []
    today_d = today
    for m in range(months):
        month_d = today_d.replace(day=1) + timedelta(days=32 * m)
        month_d = month_d.replace(day=1)
        batches.append(PurchaseBatch(
            month_index=m,
            month_label=month_d.strftime("%b %Y").lower(),
            units_to_order=per_month,
            reasoning=(f"velocity {velocity_today:.1f}/день × ~30 дн = {per_month} шт + "
                       f"safety {payload.safety_stock_days}/день"),
        ))

    reorder_point = int(round(velocity_today * (payload.lead_time_days + payload.safety_stock_days)))

    plan = PurchasePlan(
        total_units=total_units,
        avg_batch_units=per_month,
        batches=batches,
        reorder_point_units=reorder_point,
    )

    return PurchasePlanResp(
        period_from=today.isoformat(),
        period_to=horizon_to.isoformat(),
        product_id=str(pid) if pid else None,
        product_name=prod_name,
        baseline={
            "window_days": payload.baseline_window_days,
            "units_sold": units,
            "revenue": round(revenue, 2),
            "avg_price": round(avg_price, 2),
            "velocity": round(velocity_today, 2),
            "ad_spend": round(ad_spend, 2),
            "drr_pct": round(drr_pct, 2),
            "margin_pct": round(margin_pct, 1),
            "cost_price": round(cost_price or 0, 2),
            "has_cost_price": bool(cost_price and cost_price > 0),
        },
        scenarios=[scenario_A, scenario_B, scenario_C],
        purchase_plan=plan,
        note=(
            "Сценарии B и C — эвристики: -20% conversion на +10% цены и +25% velocity на +50% рекламы. "
            "Реальные эластичности зависят от категории и истории. После 3+ месяцев данные позволят "
            "подставить ваши конкретные коэффициенты."
        ),
    )


# === /progress — факт vs план (AUDIT.md A7) ===============================


class ProgressResp(BaseModel):
    goal_type: str
    goal_value: float
    period_from: str
    period_to: str
    days_passed: int
    days_remaining: int
    progress_pct: float            # факт / цель × 100
    expected_pct: float            # пропорция дней прошло
    pace_status: str               # 'ahead' | 'on_track' | 'behind' | 'far_behind'
    actual_so_far: float           # шт / ₽ — то что юзер задал в goal
    forecast_at_end: float | None  # экстраполяция на конец периода
    daily_required: float          # сколько нужно с сегодня каждый день чтобы успеть
    daily_actual: float            # текущий средний темп
    note: str


@router.get("/progress", response_model=ProgressResp)
async def plan_progress(
    goal_type: Literal["units", "profit", "revenue"],
    goal_value: float,
    period_from: str,
    period_days: int = 90,
    product_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProgressResp:
    """
    Текущий прогресс достижения цели. Сравнивает factual продажи (units/revenue/profit)
    с goal_value, оценивает pace и прогнозирует exit.

    Не сохраняет план — это stateless проверка. Юзер передаёт цель и
    период (период должен совпадать с тем что давал в /calculate).
    """
    try:
        df = date.fromisoformat(period_from)
    except ValueError:
        raise HTTPException(400, f"Неправильный period_from: {period_from}")
    dt = df + timedelta(days=period_days)
    today = date.today()
    days_passed = max(0, min((today - df).days, period_days))
    days_remaining = max(0, period_days - days_passed)
    expected_pct = (days_passed / period_days * 100) if period_days else 0

    accs_q = select(OzonAccount.id).where(
        OzonAccount.company_id == current_user.company_id,
        OzonAccount.deleted_at.is_(None),
    )
    accs = (await db.execute(accs_q)).scalars().all()
    if not accs:
        raise HTTPException(404, "Нет активных кабинетов")

    # Считаем факт за прошедшие дни периода
    pid = uuid.UUID(product_id) if product_id else None
    where = ["o.ozon_account_id = ANY(:accs)",
             "o.order_created_at >= :df", "o.order_created_at < :today",
             "o.status = 'delivered'"]
    params = {"accs": [str(a) for a in accs], "df": df, "today": today}
    if pid:
        where.append("oi.product_id = :pid")
        params["pid"] = str(pid)

    from sqlalchemy import text
    r = (await db.execute(text(f"""
        SELECT
          COALESCE(SUM(oi.quantity), 0)::int AS units,
          COALESCE(SUM(oi.price * oi.quantity), 0)::float AS revenue
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE {' AND '.join(where)}
    """), params)).first()
    actual_units = int(r.units or 0)
    actual_revenue = float(r.revenue or 0)

    # Profit оценка — revenue × средняя маржа 25% (если нет cost_price).
    # Можно улучшить дёрнув fixed margin per SKU, но для MVP оставим.
    actual_profit = actual_revenue * 0.25

    if goal_type == "units":
        actual_so_far = float(actual_units)
    elif goal_type == "revenue":
        actual_so_far = actual_revenue
    else:
        actual_so_far = actual_profit

    progress_pct = (actual_so_far / goal_value * 100) if goal_value else 0
    daily_actual = actual_so_far / days_passed if days_passed else 0
    daily_required = (goal_value - actual_so_far) / days_remaining if days_remaining else 0

    # Прогноз: текущий темп на оставшиеся дни
    forecast_at_end = actual_so_far + daily_actual * days_remaining if days_passed else None

    # Pace status
    delta_pct = progress_pct - expected_pct
    if delta_pct >= 5:
        pace_status = "ahead"
    elif delta_pct >= -5:
        pace_status = "on_track"
    elif delta_pct >= -20:
        pace_status = "behind"
    else:
        pace_status = "far_behind"

    return ProgressResp(
        goal_type=goal_type, goal_value=goal_value,
        period_from=df.isoformat(), period_to=dt.isoformat(),
        days_passed=days_passed, days_remaining=days_remaining,
        progress_pct=round(progress_pct, 1),
        expected_pct=round(expected_pct, 1),
        pace_status=pace_status,
        actual_so_far=round(actual_so_far, 2),
        forecast_at_end=round(forecast_at_end, 2) if forecast_at_end else None,
        daily_required=round(daily_required, 2),
        daily_actual=round(daily_actual, 2),
        note=(
            f"Прогресс {progress_pct:.1f}% vs ожидание {expected_pct:.1f}% по календарю. "
            f"Темп: {daily_actual:.1f}/день, нужно {daily_required:.1f}/день чтобы успеть."
        ),
    )
