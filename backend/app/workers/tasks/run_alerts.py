"""
Целевой запуск alerts engine для всех юзеров.

Беги ежечасно через Celery beat: для каждого активного юзера прогоняем
все его правила и пишем срабатывания в alerts_history (с дедупом
на сутки чтобы не спамить).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.models import User
from app.services.alerts_engine import run_alerts
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import run_celery_async


@celery_app.task(name="app.workers.tasks.run_alerts.run_all_users_alerts")
def run_all_users_alerts() -> dict:
    """Прогнать engine для всех активных юзеров. Запуск ежечасно."""
    return run_celery_async(_run_async)


async def _run_async(SessionLocal: async_sessionmaker[AsyncSession]) -> dict:
    async with SessionLocal() as db:
        users = (await db.execute(
            select(User.id).where(User.is_active.is_(True))
        )).all()
        if not users:
            return {"users": 0, "total_alerts": 0}

        total = 0
        errors = 0
        for (uid,) in users:
            try:
                res = await run_alerts(db, uid)
                total += res.get("total", 0)
            except Exception as e:
                errors += 1
                log.error("alerts_run_failed", user_id=str(uid), error=str(e))

        log.info("alerts_run_done", users=len(users), total_alerts=total, errors=errors)
        return {"users": len(users), "total_alerts": total, "errors": errors}
