"""Задачи обслуживания системы — AUDIT.md A5."""
from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import run_celery_async


@celery_app.task(name="app.workers.tasks.maintenance.cleanup_old_logs")
def cleanup_old_logs(days: int = 90) -> dict:
    """
    Удаляет sync_logs старше N дней (default 90). audit_logs — пока не трогаем
    (нужен компайл-архив в S3, отдельная задача).

    Запускается раз в сутки через Celery beat (см. celery_app.beat_schedule).
    Перед удалением считаем сколько — для лога мониторинга.
    """
    return run_celery_async(_cleanup_async, days=days)


async def _cleanup_async(SessionLocal: async_sessionmaker[AsyncSession], days: int = 90) -> dict:
    """Удалить sync_logs старше N дней."""
    async with SessionLocal() as db:
        # Считаем сколько будем удалять (для мониторинга)
        count_r = (await db.execute(text("""
            SELECT COUNT(*) FROM sync_logs WHERE started_at < NOW() - make_interval(days => :d)
        """), {"d": days})).scalar() or 0

        if count_r == 0:
            log.info("cleanup_sync_logs_nothing", days=days)
            return {"deleted": 0, "days": days}

        # DELETE с RETURNING чтобы убедиться сколько реально удалили
        deleted_r = (await db.execute(text("""
            DELETE FROM sync_logs WHERE started_at < NOW() - make_interval(days => :d)
            RETURNING id
        """), {"d": days})).rowcount
        await db.commit()

        log.info("cleanup_sync_logs", days=days, deleted=deleted_r, planned=count_r)
        return {"deleted": deleted_r, "planned": count_r, "days": days}
