"""Задачи обслуживания системы."""
from app.core.logging import log
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.maintenance.cleanup_old_logs")
def cleanup_old_logs() -> dict:
    """TODO: чистка sync_logs старше 90 дней, audit_logs архив в S3."""
    log.info("cleanup_old_logs_called")
    return {"status": "todo"}
