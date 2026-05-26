"""Синхронизация аналитики."""
from app.core.logging import log
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.sync_analytics.sync_all_analytics")
def sync_all_analytics() -> dict:
    """TODO: синхронизация метрик воронки."""
    log.info("sync_analytics_called")
    return {"status": "todo"}
