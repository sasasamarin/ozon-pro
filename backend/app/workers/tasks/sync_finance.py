"""Синхронизация финансов."""
from app.core.logging import log
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.sync_finance.sync_all_transactions")
def sync_all_transactions() -> dict:
    """TODO: синхронизация транзакций."""
    log.info("sync_transactions_called")
    return {"status": "todo"}
