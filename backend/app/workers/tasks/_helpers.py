"""
Общие хелперы для Celery-задач синхронизации.

Содержит:
- track_sync_log() — async context manager, который оборачивает работу одного
  пайплайна в строку sync_logs (started → success/failed/partial, длительность)
- load_sku_map() — словарь {ozon_sku: product_id} для конкретного OzonAccount
- tier_at_least() — guard для премиум-тарифов
"""
from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime
from typing import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import log
from app.models import OzonAccount, OzonPremiumTier, Product, SyncLog, SyncStatus


class SyncStats:
    """Изменяемый счётчик статистики синхронизации."""

    __slots__ = ("processed", "created", "updated", "failed")

    def __init__(self) -> None:
        self.processed = 0
        self.created = 0
        self.updated = 0
        self.failed = 0


@contextlib.asynccontextmanager
async def track_sync_log(
    db: AsyncSession,
    account_id: uuid.UUID,
    method: str,
) -> AsyncIterator[SyncStats]:
    """
    Обернуть пайплайн в строку sync_logs.

    Использование:
        async with track_sync_log(db, account.id, "sync_stocks") as stats:
            stats.processed += 1
            ...

    После выхода из контекста (с исключением или без) запись в sync_logs
    обновляется. Сам исключение пробрасывается дальше.
    """
    started_at = datetime.now(UTC)
    sync_log = SyncLog(
        ozon_account_id=account_id,
        method=method,
        status=SyncStatus.STARTED.value,
        started_at=started_at,
    )
    db.add(sync_log)
    await db.flush()

    stats = SyncStats()
    error_message: str | None = None
    try:
        yield stats
        sync_log.status = SyncStatus.SUCCESS.value
    except Exception as exc:  # noqa: BLE001 — записываем любую ошибку в лог
        error_message = str(exc)
        sync_log.status = SyncStatus.FAILED.value
        log.error(
            "sync_failed",
            method=method,
            account_id=str(account_id),
            error=error_message,
            exc_info=True,
        )
        raise
    finally:
        finished_at = datetime.now(UTC)
        sync_log.finished_at = finished_at
        sync_log.duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        sync_log.records_processed = stats.processed
        sync_log.records_created = stats.created
        sync_log.records_updated = stats.updated
        sync_log.records_failed = stats.failed
        sync_log.error_message = (error_message or "")[:500] or None
        # Commit done by caller — let the SyncLog row participate in the larger transaction
        await db.flush()


async def load_sku_map(
    db: AsyncSession, account_id: uuid.UUID
) -> dict[int, uuid.UUID]:
    """{ozon_sku: product.id} для всех активных товаров аккаунта.

    Используется чтобы быстро проставлять product_id в дочерних таблицах
    (stocks, price_history, order_items, analytics_daily) без N+1 запросов.
    """
    result = await db.execute(
        select(Product.id, Product.ozon_sku).where(
            Product.ozon_account_id == account_id,
            Product.deleted_at.is_(None),
        )
    )
    return {row.ozon_sku: row.id for row in result.all()}


def tier_at_least(account: OzonAccount, *required: OzonPremiumTier) -> bool:
    """True, если premium_tier кабинета входит в required-набор."""
    return account.premium_tier in {t.value for t in required}


async def get_active_accounts(db: AsyncSession) -> list[OzonAccount]:
    """Список активных кабинетов (для запуска задач по всем магазинам)."""
    result = await db.execute(
        select(OzonAccount).where(
            OzonAccount.is_active.is_(True),
            OzonAccount.deleted_at.is_(None),
        )
    )
    return list(result.scalars().all())
