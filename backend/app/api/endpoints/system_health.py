"""
GET /api/v1/system/health — статус синхронизации источников данных.
Для UI-баннера «Данные актуальны» в шапке.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User

router = APIRouter()
UTC = timezone.utc


class SourceFreshness(BaseModel):
    source: str            # 'products' | 'orders' | 'transactions' | 'analytics' | 'ads' | 'stocks'
    label: str
    last_at: str | None    # ISO когда обновлялось
    minutes_ago: int | None
    status: str            # 'fresh' | 'stale' | 'no_data'


class HealthResp(BaseModel):
    overall_status: str    # 'ok' | 'warn' | 'critical'
    fresh_count: int
    stale_count: int
    total_count: int
    sources: list[SourceFreshness]


# Свежесть теперь по sync_logs.finished_at (когда таска ПРОШЛА),
# а не max(date) данных — для date-таблиц max(date) — это начало дня,
# что давало ложную «stale» при свежем синке.
# Каждый source маппится на одно или несколько method-имён в sync_logs.
SOURCES = [
    ("products", "Товары",            ["sync_products"]),
    ("orders", "Заказы",              ["sync_orders_fbo", "sync_orders_fbs", "sync_orders"]),
    ("transactions", "Транзакции",    ["sync_finance", "sync_transactions"]),
    ("analytics", "Аналитика воронки",["sync_analytics_daily", "sync_analytics"]),
    ("ads", "Реклама",                ["sync_ad_statistics", "sync_ads", "sync_ad_campaigns"]),
    ("stocks", "Остатки",             ["sync_stocks"]),
]

# Сколько минут считаем «свежим» для каждого источника
FRESH_THRESHOLD_MIN = {
    "products": 6 * 60,        # 6 часов (синк каждый час)
    "orders": 60,              # 1 час (синк каждые 15 мин)
    "transactions": 30 * 60,   # 30 часов (синк раз в сутки)
    "analytics": 30 * 60,      # 30 часов (синк раз в сутки)
    "ads": 30 * 60,            # 30 часов
    "stocks": 6 * 60,          # 6 часов
}


@router.get("/health", response_model=HealthResp)
async def get_system_health(
    current_user: User = Depends(get_current_user),  # для авторизации
    db: AsyncSession = Depends(get_db),
) -> HealthResp:
    now = datetime.now(UTC)
    fresh = stale = 0
    out: list[SourceFreshness] = []

    for code, label, methods in SOURCES:
        try:
            last_at = (await db.execute(text("""
                SELECT MAX(finished_at) FROM sync_logs
                WHERE method = ANY(:methods) AND status = 'success'
            """), {"methods": methods})).scalar()
        except Exception:
            last_at = None

        if last_at is None:
            out.append(SourceFreshness(
                source=code, label=label, last_at=None, minutes_ago=None,
                status="no_data",
            ))
            continue

        # last_at может быть naive (если timescale chunk без TZ)
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=UTC)
        delta_min = int((now - last_at).total_seconds() / 60)
        threshold = FRESH_THRESHOLD_MIN.get(code, 6 * 60)
        status = "fresh" if delta_min <= threshold else "stale"
        if status == "fresh": fresh += 1
        else: stale += 1
        out.append(SourceFreshness(
            source=code, label=label,
            last_at=last_at.isoformat(),
            minutes_ago=delta_min,
            status=status,
        ))

    total = len([s for s in out if s.status != "no_data"])
    overall = "ok" if stale == 0 else "warn" if stale <= 2 else "critical"
    return HealthResp(
        overall_status=overall,
        fresh_count=fresh, stale_count=stale, total_count=total,
        sources=out,
    )
