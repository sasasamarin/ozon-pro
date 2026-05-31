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
    worst_diff_pct: float | None  # самое большое расхождение по последним сверкам
    rows_count: int


@router.get("/realization", response_model=list[ReconcileRow])
async def list_reconciliations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ReconcileRow]:
    rows = (await db.execute(text("""
        SELECT r.ozon_account_id, a.name AS cabinet_name, r.year, r.month,
               r.total_revenue::float, r.total_payout_real::float, r.total_payout_model::float,
               r.diff_pct::float, r.created_at
        FROM realization_reconciliation r
        JOIN ozon_accounts a ON a.id = r.ozon_account_id
        WHERE a.company_id = :cid
        ORDER BY r.year DESC, r.month DESC, a.name
    """), {"cid": str(current_user.company_id)})).all()
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
    rows = (await db.execute(text("""
        SELECT a.name AS cabinet_name, r.sku_breakdown
        FROM realization_reconciliation r
        JOIN ozon_accounts a ON a.id = r.ozon_account_id
        WHERE a.company_id = :cid AND r.year = :y AND r.month = :m
    """), {"cid": str(current_user.company_id), "y": year, "m": month})).all()
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
    """Статус для UI-баннера: 🟢 свежая сверка ОК | 🔴 расхождение."""
    # Самая свежая сверка для каждого кабинета
    rows = (await db.execute(text("""
        SELECT DISTINCT ON (r.ozon_account_id)
               r.ozon_account_id, r.diff_pct::float, r.created_at, r.year, r.month
        FROM realization_reconciliation r
        JOIN ozon_accounts a ON a.id = r.ozon_account_id
        WHERE a.company_id = :cid
        ORDER BY r.ozon_account_id, r.year DESC, r.month DESC, r.created_at DESC
    """), {"cid": str(current_user.company_id)})).all()

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

    if worst is not None and worst > ALERT_THRESHOLD_PCT:
        return ReconcileStatus(
            status="warn",
            title=f"Расхождение с Ozon: {worst:.1f}%",
            description=f"Наша оперативная модель отличается от отчёта Ozon. "
                        f"Проверь Настройки → Сверка реализации для деталей по SKU.",
            last_reconciled_at=last_at.isoformat() if last_at else None,
            worst_diff_pct=worst, rows_count=len(rows),
        )
    return ReconcileStatus(
        status="ok",
        title="Сверено с отчётом Ozon",
        description=f"Модель совпадает с реализацией Ozon (худшее расхождение {worst or 0:.1f}%). "
                    f"Можно доверять цифрам прибыли.",
        last_reconciled_at=last_at.isoformat() if last_at else None,
        worst_diff_pct=worst, rows_count=len(rows),
    )
