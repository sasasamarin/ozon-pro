"""
API для авто-сверки финмодели Flowoi с отчётом Ozon.

GET /api/v1/reconciliation/realization
    Последние результаты сверки по всем кабинетам компании.

GET /api/v1/reconciliation/realization/{year}/{month}
    Детальная разбивка по SKU за конкретный месяц.

POST /api/v1/reconciliation/realization/run
    Ручной запуск сверки (для админа).

GET /api/v1/reconciliation/status
    Статус «свежей» сверки для UI-баннера: зелёная галка / алерт.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.deps_cabinets import get_accessible_cabinet_ids
from app.db.session import get_db
from app.models import OzonAccount, User

router = APIRouter()

ALERT_THRESHOLD_PCT = 5.0


class ReconcileRow(BaseModel):
    ozon_account_id: str
    cabinet_name: str
    year: int
    month: int
    total_revenue: float | None
    total_payout_real: float | None
    total_payout_model: float | None
    diff_pct: float | None
    alert: bool                # True если |diff_pct| > порога
    created_at: str


class ReconcileStatus(BaseModel):
    status: str                # 'ok' | 'warn' | 'no_data'
    title: str
    description: str
    last_reconciled_at: str | None
    worst_diff_pct: float | None    # самое большое расхождение по последним сверкам
    rows_count: int
    # ЗА КАКОЙ ПЕРИОД сверены данные (не дата прогона!)
    data_period_year: int | None = None
    data_period_month: int | None = None
    data_period_label: str | None = None  # "Апрель 2026" — для UI


@router.get("/realization", response_model=list[ReconcileRow])
async def list_reconciliations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ReconcileRow]:
    accessible = await get_accessible_cabinet_ids(db, current_user)
    extra_filter = ""
    params: dict = {"cid": str(current_user.company_id)}
    if accessible is not None:
        if not accessible:
            return []
        extra_filter = " AND a.id = ANY(:accessible_ids)"
        params["accessible_ids"] = [str(c) for c in accessible]

    rows = (await db.execute(text(f"""
        SELECT r.ozon_account_id, a.name AS cabinet_name, r.year, r.month,
               r.total_revenue::float, r.total_payout_real::float, r.total_payout_model::float,
               r.diff_pct::float, r.created_at
        FROM realization_reconciliation r
        JOIN ozon_accounts a ON a.id = r.ozon_account_id
        WHERE a.company_id = :cid{extra_filter}
        ORDER BY r.year DESC, r.month DESC, a.name
    """), params)).all()
    out = []
    for r in rows:
        diff = float(r.diff_pct) if r.diff_pct is not None else None
        out.append(ReconcileRow(
            ozon_account_id=str(r.ozon_account_id),
            cabinet_name=r.cabinet_name,
            year=r.year, month=r.month,
            total_revenue=float(r.total_revenue) if r.total_revenue else None,
            total_payout_real=float(r.total_payout_real) if r.total_payout_real else None,
            total_payout_model=float(r.total_payout_model) if r.total_payout_model else None,
            diff_pct=diff,
            alert=(abs(diff) > ALERT_THRESHOLD_PCT) if diff is not None else False,
            created_at=r.created_at.isoformat() if r.created_at else "",
        ))
    return out


@router.get("/realization/{year}/{month}", response_model=list[dict])
async def get_reconciliation_detail(
    year: int, month: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Детальная разбивка по SKU + кабинетам за этот месяц."""
    accessible = await get_accessible_cabinet_ids(db, current_user)
    extra_filter = ""
    params: dict = {"cid": str(current_user.company_id), "y": year, "m": month}
    if accessible is not None:
        if not accessible:
            return []
        extra_filter = " AND a.id = ANY(:accessible_ids)"
        params["accessible_ids"] = [str(c) for c in accessible]

    rows = (await db.execute(text(f"""
        SELECT a.name AS cabinet_name, r.sku_breakdown
        FROM realization_reconciliation r
        JOIN ozon_accounts a ON a.id = r.ozon_account_id
        WHERE a.company_id = :cid AND r.year = :y AND r.month = :m{extra_filter}
    """), params)).all()
    out: list[dict] = []
    for r in rows:
        cabinet = r.cabinet_name
        for sku_row in (r.sku_breakdown or []):
            out.append({"cabinet": cabinet, **sku_row})
    return out


@router.post("/realization/run", response_model=dict)
async def run_reconciliation(
    year: int | None = None,
    month: int | None = None,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Ручной запуск сверки. Возвращает task_id для отслеживания."""
    from app.workers.tasks.reconcile_realization import reconcile_realization
    task = reconcile_realization.delay(year=year, month=month)
    return {"task_id": task.id, "year": year, "month": month}


@router.get("/status", response_model=ReconcileStatus)
async def reconciliation_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReconcileStatus:
    """Статус для UI-баннера: свежая сверка ОК | расхождение."""
    accessible = await get_accessible_cabinet_ids(db, current_user)
    extra_filter = ""
    params: dict = {"cid": str(current_user.company_id)}
    if accessible is not None:
        if not accessible:
            return ReconcileStatus(
                status="no_data", title="Сверка не запускалась",
                description="Нет доступных кабинетов.",
                last_reconciled_at=None, worst_diff_pct=None, rows_count=0,
            )
        extra_filter = " AND a.id = ANY(:accessible_ids)"
        params["accessible_ids"] = [str(c) for c in accessible]

    # Самая свежая сверка для каждого кабинета
    rows = (await db.execute(text(f"""
        SELECT DISTINCT ON (r.ozon_account_id)
               r.ozon_account_id, r.diff_pct::float, r.created_at, r.year, r.month
        FROM realization_reconciliation r
        JOIN ozon_accounts a ON a.id = r.ozon_account_id
        WHERE a.company_id = :cid{extra_filter}
        ORDER BY r.ozon_account_id, r.year DESC, r.month DESC, r.created_at DESC
    """), params)).all()

    if not rows:
        return ReconcileStatus(
            status="no_data", title="Сверка не запускалась",
            description="Авто-сверка с отчётом Ozon /v2/finance/realization выполняется раз в неделю. "
                       "Первый отчёт Ozon формирует с лагом ~15 дней после конца месяца.",
            last_reconciled_at=None, worst_diff_pct=None, rows_count=0,
        )

    diffs = [abs(float(r.diff_pct)) for r in rows if r.diff_pct is not None]
    worst = max(diffs) if diffs else None
    last_at = max(r.created_at for r in rows if r.created_at)

    # Самый свежий ПЕРИОД сверки — за какой месяц данные.
    # ВАЖНО: это НЕ дата прогона. Реализация Ozon формируется с лагом ~15 дней,
    # так что свежий period обычно = «прошлый месяц». Текущий незакрытый месяц
    # ещё нельзя сверить — данных в realization нет.
    periods = [(r.year, r.month) for r in rows]
    if periods:
        max_y, max_m = max(periods)
        MONTHS_RU = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                     "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
        period_label = f"{MONTHS_RU[max_m]} {max_y}"
    else:
        max_y = max_m = None
        period_label = None

    # Конец сверенного периода (последний день месяца) — чтобы юзер видел
    # «данные актуальны по DD.MM», не путал с датой прогона.
    period_end_str: str | None = None
    if max_y and max_m:
        from datetime import date as _d
        from calendar import monthrange as _mr
        period_end_str = _d(max_y, max_m, _mr(max_y, max_m)[1]).strftime("%d.%m.%Y")

    if worst is not None and worst > ALERT_THRESHOLD_PCT:
        return ReconcileStatus(
            status="warn",
            title=f"Расхождение с Ozon: {worst:.1f}%",
            description=f"Наша модель отличается от отчёта Ozon за {period_label}. "
                        f"Сверка покрывает данные ПО {period_end_str}. "
                        f"Текущий месяц не сверен — отчёт Ozon формируется с лагом ~15 дней. "
                        f"Подробности: Настройки → Сверка реализации.",
            last_reconciled_at=last_at.isoformat() if last_at else None,
            worst_diff_pct=worst, rows_count=len(rows),
            data_period_year=max_y, data_period_month=max_m,
            data_period_label=period_label,
        )
    return ReconcileStatus(
        status="ok",
        title=f"Сверено · {period_label}" if period_label else "Сверено с Ozon",
        description=f"Модель совпадает с реализацией Ozon за {period_label}"
                    f" (худшее расхождение {worst or 0:.1f}%). "
                    f"Данные актуальны ПО {period_end_str}. "
                    f"Текущий месяц не сверен — отчёт Ozon формируется с лагом ~15 дней. "
                    f"Можно доверять цифрам прибыли за прошлые месяцы.",
        last_reconciled_at=last_at.isoformat() if last_at else None,
        worst_diff_pct=worst, rows_count=len(rows),
        data_period_year=max_y, data_period_month=max_m,
        data_period_label=period_label,
    )
