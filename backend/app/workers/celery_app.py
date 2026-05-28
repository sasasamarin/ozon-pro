"""
Celery приложение для фоновых задач.

Задачи:
- Sync товаров (каждый час)
- Sync остатков (каждые 30 минут)
- Sync цен (каждый час)
- Sync заказов (каждые 15 минут)
- Sync транзакций (раз в день в 3:00)
- Sync аналитики (раз в день в 4:00)
- Очистка старых логов (раз в неделю)

Запуск:
    docker-compose up -d worker beat
"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings


celery_app = Celery(
    "ozon_pro",
    broker=str(settings.CELERY_BROKER_URL),
    backend=str(settings.CELERY_RESULT_BACKEND),
    include=[
        "app.workers.tasks.sync_products",
        "app.workers.tasks.sync_orders",
        "app.workers.tasks.sync_finance",
        "app.workers.tasks.sync_analytics",
        "app.workers.tasks.sync_ads",
        "app.workers.tasks.sync_marketplace",
        "app.workers.tasks.sync_communications",
        "app.workers.tasks.maintenance",
        "app.workers.tasks.recompute_recommendations",
    ],
)


# Конфигурация Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,

    # Ограничения
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_time_limit=600,  # максимум 10 минут на задачу
    task_soft_time_limit=540,  # мягкий лимит 9 минут

    # Повторы при ошибке
    task_default_retry_delay=60,  # 1 минута
    task_max_retries=3,
)


# Расписание задач (Celery Beat)
celery_app.conf.beat_schedule = {
    # === SYNC ===
    "sync-products-every-hour": {
        "task": "app.workers.tasks.sync_products.sync_all_products",
        "schedule": crontab(minute=0),  # каждый час в :00
    },
    "sync-stocks-every-30-min": {
        "task": "app.workers.tasks.sync_products.sync_all_stocks",
        "schedule": crontab(minute="*/30"),  # каждые 30 минут
    },
    "sync-prices-every-hour": {
        "task": "app.workers.tasks.sync_products.sync_all_prices",
        "schedule": crontab(minute=15),  # каждый час в :15
    },
    "sync-orders-every-15-min": {
        "task": "app.workers.tasks.sync_orders.sync_all_orders",
        "schedule": crontab(minute="*/15"),
    },
    "sync-transactions-daily": {
        "task": "app.workers.tasks.sync_finance.sync_all_transactions",
        "schedule": crontab(hour=3, minute=0),  # каждый день в 3:00
    },
    "sync-analytics-daily": {
        "task": "app.workers.tasks.sync_analytics.sync_all_analytics",
        "schedule": crontab(hour=4, minute=0),  # каждый день в 4:00
    },
    "sync-ad-campaigns-hourly": {
        "task": "app.workers.tasks.sync_ads.sync_all_ad_campaigns",
        "schedule": crontab(minute=45),
    },
    "sync-ad-statistics-daily": {
        "task": "app.workers.tasks.sync_ads.sync_all_ad_statistics",
        "schedule": crontab(hour=5, minute=0),
    },

    # === НОВЫЕ ТАСКИ (Phase 2 → A) ===
    "sync-warehouse-stocks-daily": {
        "task": "app.workers.tasks.sync_products.sync_all_warehouse_stocks",
        "schedule": crontab(hour=2, minute=30),  # ночью — снимок складов
    },
    "sync-returns-hourly": {
        "task": "app.workers.tasks.sync_marketplace.sync_all_returns",
        "schedule": crontab(minute=20),  # incremental — последние 30 дней
    },
    "sync-cancellations-hourly": {
        "task": "app.workers.tasks.sync_marketplace.sync_all_cancellations",
        "schedule": crontab(minute=25),
    },
    "sync-realization-daily": {
        "task": "app.workers.tasks.sync_marketplace.sync_all_realization",
        "schedule": crontab(hour=6, minute=0),  # после ad-statistics
    },
    "sync-reviews-4x-day": {
        "task": "app.workers.tasks.sync_communications.sync_all_reviews",
        "schedule": crontab(hour="*/6", minute=10),  # 00:10, 06:10, 12:10, 18:10
    },
    "sync-questions-4x-day": {
        "task": "app.workers.tasks.sync_communications.sync_all_questions",
        "schedule": crontab(hour="*/6", minute=15),
    },
    "sync-chats-every-30min": {
        "task": "app.workers.tasks.sync_communications.sync_all_chats",
        "schedule": crontab(minute="*/30"),
    },

    # === FORECASTING ===
    "recompute-recommendations-nightly": {
        "task": "app.workers.tasks.recompute_recommendations.recompute_all",
        "schedule": crontab(hour=3, minute=30),  # после sync-transactions-daily (3:00)
    },

    # === ОБСЛУЖИВАНИЕ ===
    "cleanup-old-logs-weekly": {
        "task": "app.workers.tasks.maintenance.cleanup_old_logs",
        "schedule": crontab(day_of_week=0, hour=2, minute=0),  # вс 2:00
    },
}
