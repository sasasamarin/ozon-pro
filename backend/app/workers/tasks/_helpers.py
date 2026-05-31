"""
Общие хелперы для Celery-задач синхронизации.

Содержит:
- run_celery_async() — обёртка для запуска async-кода из Celery-task с фреш
  engine на каждый вызов (фикс «Task attached to a different loop»)
- track_sync_log() — async context manager, который оборачивает работу одного
  пайплайна в строку sync_logs (started → success/failed/partial, длительность)
- load_sku_map() — словарь {ozon_sku: product_id} для конкретного OzonAccount
- tier_at_least() — guard для премиум-тарифов
"""
from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime
from typing import AsyncIterator, Awaitable, Callable, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.db.session import make_engine_and_session
from app.models import OzonAccount, OzonPremiumTier, Product, SyncLog, SyncStatus

T = TypeVar("T")


def run_celery_async(
    coro_factory: Callable[..., Awaitable[T]],
    *args,
    **kwargs,
) -> T:
    """
    Запустить async-функцию из Celery-task с фреш engine.

    Каждая Celery-task должна вызывать SQL через async SQLAlchemy. Celery
    prefork worker переиспользует процесс между task'ами, а `asyncio.run()`
    создаёт новый event loop при каждом вызове. asyncpg-движок, привязанный
    к старому loop'у, ломается во втором task'е с
    «Task attached to a different loop».

    Решение: каждая task получает СВОЙ engine + AsyncSessionLocal, привязанный
    к текущему loop'у, и диспозит его по завершении.

    Использование:
        @celery_app.task
        def sync_all_X():
            return run_celery_async(_sync_all_X_async)

        async def _sync_all_X_async(SessionLocal):
            async with SessionLocal() as db:
                ...
    """
    async def _main() -> T:
        # Меньший пул для Celery — большинство тасок коротко-живущие.
        engine, session_factory = make_engine_and_session(pool_size=3, max_overflow=2)
        try:
            return await coro_factory(session_factory, *args, **kwargs)
        finally:
            await engine.dispose()

    return asyncio.run(_main())


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


async def get_sync_cursor(
    SessionFactory: async_sessionmaker[AsyncSession],
    *, cabinet_id: uuid.UUID, endpoint: str,
) -> str | None:
    """Читает sync_state.last_cursor для (cabinet, endpoint). None если нет.

    Универсальный курсор-API для всех sync-task'ов:
    - analytics: ISO дата ("2026-05-31") — до какого дня всё синкнуто
    - orders/transactions: ISO datetime — до какого момента всё синкнуто
    - returns: ISO дата — last return_date
    """
    from app.models import SyncState
    from sqlalchemy import select
    async with SessionFactory() as db:
        row = (await db.execute(
            select(SyncState.last_cursor).where(
                SyncState.cabinet_id == cabinet_id,
                SyncState.endpoint == endpoint,
            )
        )).first()
    return row.last_cursor if row else None


async def save_sync_cursor(
    SessionFactory: async_sessionmaker[AsyncSession],
    *, cabinet_id: uuid.UUID, endpoint: str, cursor: str,
    status: str = "ok", error: str | None = None,
) -> None:
    """Upsert sync_state.last_cursor для (cabinet, endpoint)."""
    from app.models import SyncState
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    async with SessionFactory() as db:
        stmt = pg_insert(SyncState).values(
            cabinet_id=cabinet_id, endpoint=endpoint,
            last_cursor=cursor, last_synced_at=datetime.now(UTC),
            status=status, error_message=(error[:500] if error else None),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["cabinet_id", "endpoint"],
            set_={
                "last_cursor": stmt.excluded.last_cursor,
                "last_synced_at": stmt.excluded.last_synced_at,
                "status": stmt.excluded.status,
                "error_message": stmt.excluded.error_message,
            },
        )
        await db.execute(stmt)
        await db.commit()


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


async def load_extended_sku_map(
    db: AsyncSession, account_id: uuid.UUID
) -> dict[int, uuid.UUID]:
    """Расширенный {ozon_sku: product.id} — primary + все варианты складов.

    Зачем нужно: Ozon в /v1/analytics/data, /v3/posting/* и подобных
    endpoint'ах возвращает SKU **варианта склада** (FBO/FBS), который ≠
    primary `products.ozon_sku` из /v3/product/list. Без этой расширенной
    карты analytics-backfill писал 0 строк (все entries пропускались).

    Дополняем primary-карту всеми SKU из order_items (где product_id уже
    был привязан через offer_id-матчинг при синке заказов). Это даёт полный
    маппинг variant→product для большинства SKU.
    """
    from app.models import Order, OrderItem  # local import чтобы избежать circular

    base = await load_sku_map(db, account_id)

    # SKU вариантов из order_items
    rows = await db.execute(
        select(OrderItem.ozon_sku, OrderItem.product_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.ozon_account_id == account_id,
            OrderItem.product_id.is_not(None),
            OrderItem.ozon_sku.is_not(None),
        )
        .distinct()
    )
    for sku, pid in rows.all():
        if sku and pid and sku not in base:
            base[sku] = pid
    return base


async def load_offer_id_map(
    db: AsyncSession, account_id: uuid.UUID
) -> dict[str, uuid.UUID]:
    """{offer_id: product.id} для всех активных товаров аккаунта.

    Зачем отдельно от load_sku_map: Ozon в /v3/product/list отдаёт ОДИН
    `sku` (primary), а в /v3/posting/fbo/list возвращает SKU варианта
    склада (FBO/FBS — разные числа), который не совпадает с primary.
    Поэтому order_items надо матчить по offer_id, который у Ozon
    стабильный и одинаковый везде.
    """
    result = await db.execute(
        select(Product.id, Product.offer_id).where(
            Product.ozon_account_id == account_id,
            Product.deleted_at.is_(None),
        )
    )
    return {row.offer_id: row.id for row in result.all() if row.offer_id}


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
