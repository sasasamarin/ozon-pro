"""
/api/v1/alerts — управление алертами и правилами.

Endpoints:
  GET    /alerts/active        — открытые
  GET    /alerts/history       — журнал
  POST   /alerts/{id}/resolve  — закрыть
  POST   /alerts/run-checks    — прогнать engine сейчас
  GET    /alerts/rules         — список правил
  POST   /alerts/rules         — создать правило
  PATCH  /alerts/rules/{id}    — обновить
  DELETE /alerts/rules/{id}    — удалить
  POST   /alerts/seed-defaults — заполнить дефолтными правилами
  GET    /alerts/channels      — список каналов (агрегат из правил)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, UTC

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.models.alert import (
    AlertHistory, AlertMarkerType, AlertRule, AlertSeverity,
)
from app.services.alerts_engine import run_alerts, seed_default_rules


router = APIRouter()


# === Schemas ===

class AlertRow(BaseModel):
    id: str
    marker_type: str
    severity: str
    message: str
    ozon_account_id: str | None
    triggered_at: str
    resolved_at: str | None
    resolved_by_user_id: str | None


class AlertRuleRow(BaseModel):
    id: str
    marker_type: str
    is_active: bool
    threshold_json: dict
    quiet_hours_json: dict | None
    channels_json: list
    ozon_account_id: str | None


class AlertRuleCreate(BaseModel):
    marker_type: str
    threshold_json: dict = {}
    quiet_hours_json: dict | None = None
    channels_json: list = ["in_app"]
    ozon_account_id: str | None = None
    is_active: bool = True


class AlertRuleUpdate(BaseModel):
    threshold_json: dict | None = None
    quiet_hours_json: dict | None = None
    channels_json: list | None = None
    is_active: bool | None = None


class ChannelSummary(BaseModel):
    kind: str
    enabled_rules_count: int
    total_rules_count: int


# === Endpoints: alerts ===

def _row(a: AlertHistory) -> AlertRow:
    return AlertRow(
        id=str(a.id),
        marker_type=a.marker_type,
        severity=a.severity,
        message=a.message,
        ozon_account_id=str(a.ozon_account_id) if a.ozon_account_id else None,
        triggered_at=a.triggered_at.isoformat() if a.triggered_at else "",
        resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
        resolved_by_user_id=str(a.resolved_by_user_id) if a.resolved_by_user_id else None,
    )


@router.get("/active", response_model=list[AlertRow])
async def list_active(
    severity: str | None = Query(None),
    marker_type: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AlertRow]:
    q = select(AlertHistory).where(
        AlertHistory.user_id == current_user.id,
        AlertHistory.resolved_at.is_(None),
    )
    if severity:
        q = q.where(AlertHistory.severity == severity)
    if marker_type:
        q = q.where(AlertHistory.marker_type == marker_type)
    q = q.order_by(AlertHistory.triggered_at.desc()).limit(200)
    rows = (await db.execute(q)).scalars().all()
    return [_row(a) for a in rows]


@router.get("/history", response_model=list[AlertRow])
async def list_history(
    days: int = Query(30, ge=1, le=365),
    marker_type: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AlertRow]:
    df = datetime.now(UTC) - timedelta(days=days)
    q = select(AlertHistory).where(
        AlertHistory.user_id == current_user.id,
        AlertHistory.triggered_at >= df,
    )
    if marker_type:
        q = q.where(AlertHistory.marker_type == marker_type)
    q = q.order_by(AlertHistory.triggered_at.desc()).limit(500)
    rows = (await db.execute(q)).scalars().all()
    return [_row(a) for a in rows]


@router.post("/{alert_id}/resolve", response_model=AlertRow)
async def resolve_alert(
    alert_id: str,
    note: str = Query("", max_length=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertRow:
    try:
        aid = uuid.UUID(alert_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")
    a = (await db.execute(
        select(AlertHistory).where(
            AlertHistory.id == aid, AlertHistory.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Alert не найден")
    a.resolved_at = datetime.now(UTC)
    a.resolved_by_user_id = current_user.id
    await db.commit()
    await db.refresh(a)
    return _row(a)


@router.post("/run-checks")
async def run_checks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Прогнать engine сейчас. Возвращает {total, by_type}."""
    return await run_alerts(db, current_user.id)


# === Endpoints: rules ===

@router.get("/rules", response_model=list[AlertRuleRow])
async def list_rules(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AlertRuleRow]:
    rows = (await db.execute(
        select(AlertRule).where(AlertRule.user_id == current_user.id)
        .order_by(AlertRule.marker_type)
    )).scalars().all()
    return [
        AlertRuleRow(
            id=str(r.id),
            marker_type=r.marker_type,
            is_active=r.is_active,
            threshold_json=r.threshold_json or {},
            quiet_hours_json=r.quiet_hours_json,
            channels_json=r.channels_json or [],
            ozon_account_id=str(r.ozon_account_id) if r.ozon_account_id else None,
        )
        for r in rows
    ]


@router.post("/rules", response_model=AlertRuleRow)
async def create_rule(
    payload: AlertRuleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertRuleRow:
    # Валидация типа
    valid_types = {t.value for t in AlertMarkerType}
    if payload.marker_type not in valid_types:
        raise HTTPException(400, f"Неизвестный тип. Доступны: {sorted(valid_types)}")

    rule = AlertRule(
        user_id=current_user.id,
        marker_type=payload.marker_type,
        threshold_json=payload.threshold_json,
        quiet_hours_json=payload.quiet_hours_json,
        channels_json=payload.channels_json,
        is_active=payload.is_active,
        ozon_account_id=uuid.UUID(payload.ozon_account_id) if payload.ozon_account_id else None,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return AlertRuleRow(
        id=str(rule.id), marker_type=rule.marker_type, is_active=rule.is_active,
        threshold_json=rule.threshold_json or {}, quiet_hours_json=rule.quiet_hours_json,
        channels_json=rule.channels_json or [],
        ozon_account_id=str(rule.ozon_account_id) if rule.ozon_account_id else None,
    )


@router.patch("/rules/{rule_id}", response_model=AlertRuleRow)
async def update_rule(
    rule_id: str,
    payload: AlertRuleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertRuleRow:
    try:
        rid = uuid.UUID(rule_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")
    r = (await db.execute(
        select(AlertRule).where(
            AlertRule.id == rid, AlertRule.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Правило не найдено")
    if payload.threshold_json is not None:
        r.threshold_json = payload.threshold_json
    if payload.quiet_hours_json is not None:
        r.quiet_hours_json = payload.quiet_hours_json
    if payload.channels_json is not None:
        r.channels_json = payload.channels_json
    if payload.is_active is not None:
        r.is_active = payload.is_active
    await db.commit()
    await db.refresh(r)
    return AlertRuleRow(
        id=str(r.id), marker_type=r.marker_type, is_active=r.is_active,
        threshold_json=r.threshold_json or {}, quiet_hours_json=r.quiet_hours_json,
        channels_json=r.channels_json or [],
        ozon_account_id=str(r.ozon_account_id) if r.ozon_account_id else None,
    )


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        rid = uuid.UUID(rule_id)
    except ValueError:
        raise HTTPException(400, "Невалидный id")
    r = (await db.execute(
        select(AlertRule).where(
            AlertRule.id == rid, AlertRule.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Правило не найдено")
    await db.delete(r)
    await db.commit()
    return {"ok": True}


@router.post("/seed-defaults")
async def seed_defaults(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Создать дефолтные правила (если нет)."""
    n = await seed_default_rules(db, current_user.id)
    return {"created": n}


# === Channels (summary view) ===

@router.get("/channels", response_model=list[ChannelSummary])
async def list_channels(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChannelSummary]:
    """Сводка использования каналов в правилах юзера."""
    rules = (await db.execute(
        select(AlertRule).where(AlertRule.user_id == current_user.id)
    )).scalars().all()

    # Подсчёт
    channel_data: dict[str, dict[str, int]] = {}
    for r in rules:
        for ch in (r.channels_json or []):
            d = channel_data.setdefault(ch, {"enabled": 0, "total": 0})
            d["total"] += 1
            if r.is_active:
                d["enabled"] += 1

    # Каноничный список даже если канал не используется
    canonical = ["in_app", "telegram", "email", "webhook"]
    for k in canonical:
        if k not in channel_data:
            channel_data[k] = {"enabled": 0, "total": 0}

    return [
        ChannelSummary(
            kind=k,
            enabled_rules_count=v["enabled"],
            total_rules_count=v["total"],
        )
        for k, v in sorted(channel_data.items())
    ]
