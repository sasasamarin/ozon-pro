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
        "app.workers.tasks.sync_financing",
        "app.workers.tasks.maintenance",
        "app.workers.tasks.recompute_recommendations",
        "app.workers.tasks.enrich_customer_price",
        "app.workers.tasks.backfill_customer_price_estimate",
        "app.workers.tasks.reconcile_realization",
        "app.workers.tasks.sync_category_tree",
        "app.workers.tasks.sync_placement_reports",
        "app.workers.tasks.sync_premium",
        "app.workers.tasks.run_alerts",
        "app.workers.tasks.alerts_digest",
        "app.workers.tasks.snapshot_commissions",
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
        # default days_window=3 — лёгкий sliding pull свежих заказов
    },
    # P0 #5: глубокий sliding window раз в сутки — ловит мутации (отмены/
    # доставка с лагом, статус обновился задним числом). Из диагностики:
    # 268 заказов KOO мутируют в окне 1-7 дней — 30 дней покрывает с запасом.
    "sync-orders-deep-90-days-daily": {
        "task": "app.workers.tasks.sync_orders.sync_all_orders",
        "schedule": crontab(hour=2, minute=30),  # 02:30 UTC (тихий час)
        # 90 дней нужны для прогнозов сезонности в /sales-plan
        "kwargs": {"days_window": 90},
    },
    # Догоняем customer_price для свежих postings (хвост 500 шт).
    # Полный backfill 29k запускается вручную:
    #   docker exec ozon_worker celery -A app.workers.celery_app call enrich_customer_price --kwargs '{"max_postings": 30000}'
    "enrich-customer-price-hourly": {
        "task": "enrich_customer_price",
        "schedule": crontab(minute=10),
        "kwargs": {"max_postings": 500},
    },
    # Авто-сверка финмодели с отчётом Ozon /v2/finance/realization.
    # Раз в неделю по понедельникам в 06:00 — берём предыдущий месяц.
    # Realization Ozon формирует с лагом ~15 дней, так что свежий отчёт
    # подхватится в начале следующего месяца.
    "reconcile-realization-weekly": {
        "task": "reconcile_realization",
        "schedule": crontab(hour=6, minute=0, day_of_week=1),
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
    # Per-SKU «Оплата за клик» за вчера → ad_product_daily. Метод products/sku
    # отдаёт только сегодня/вчера, копим ежедневно. 5:30 UTC = 8:30 МСК (вчера
    # финализировано после 3:00 МСК).
    "sync-ad-product-sku-daily": {
        "task": "app.workers.tasks.sync_ads.sync_all_ad_product_sku",
        "schedule": crontab(hour=5, minute=30),
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
    "sync-financing-daily": {
        # Перенос операций EarlyPaymentAccrual + FlexiblePaymentSchedule
        # из transactions → ozon_financing + movements. Бежим после sync_transactions.
        "task": "app.workers.tasks.sync_financing.sync_all_financing",
        "schedule": crontab(hour=3, minute=30),
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

    # === ALERTS ===
    # Прогоняем правила алертов ежечасно. Engine с дедупом на сутки —
    # один тип алерта на entity не дублируется чаще раза в день.
    "run-alerts-hourly": {
        "task": "app.workers.tasks.run_alerts.run_all_users_alerts",
        "schedule": crontab(minute=50),  # каждый час в :50 (после всех sync-задач)
    },
    # Email-дайджест активных алертов: раз в день в 09:00 UTC (12:00 МСК)
    "send-alert-digests-daily": {
        "task": "app.workers.tasks.alerts_digest.send_daily_digests",
        "schedule": crontab(hour=9, minute=0),
    },
    # Snapshot комиссий — ежедневно после sync-products (sync в :00, мы в :05)
    "snapshot-commissions-daily": {
        "task": "app.workers.tasks.snapshot_commissions.snapshot_all",
        "schedule": crontab(hour=4, minute=5),  # после daily sync
    },

    # === ОБСЛУЖИВАНИЕ ===
    "cleanup-old-logs-weekly": {
        "task": "app.workers.tasks.maintenance.cleanup_old_logs",
        "schedule": crontab(day_of_week=0, hour=2, minute=0),  # вс 2:00
    },
    # Дерево категорий Ozon — каталог стабильный, раз в неделю достаточно
    "sync-category-tree-weekly": {
        "task": "app.workers.tasks.sync_category_tree.sync_category_tree",
        "schedule": crontab(day_of_week=0, hour=1, minute=0),  # вс 01:00 UTC
    },
    # Отчёты «Размещение по товарам» (seller_placement_by_products) — точные
    # per-SKU финрасходы (storage/реклама/эквайринг). Ozon генерирует их
    # асинхронно, мы просто скачиваем готовые из /v1/report/list.
    # Раз в час достаточно: отчёты появляются после ручной выгрузки в UI
    # либо по автоматическому расписанию Ozon (обычно после закрытия месяца).
    "sync-placement-reports-hourly": {
        "task": "app.workers.tasks.sync_placement_reports.sync_placement_reports",
        "schedule": crontab(minute=15),  # каждый час в :15
    },
    # Backup БД работает на хосте VPS через systemd timer (scripts/backup_db.sh).
    # Решение принято осознанно: pg_dump на хосте не зависит от Docker rebuild
    # и не требует postgresql-client в backend образе.
}
