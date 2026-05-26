"""Синхронизация заказов."""
from app.core.logging import log
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.sync_orders.sync_all_orders")
def sync_all_orders() -> dict:
    """TODO: синхронизация заказов FBO и FBS."""
    log.info("sync_orders_called")
    return {"status": "todo"}
