"""
Синхронизация товаров с Озона.

Каждый магазин обрабатывается параллельно.
Логируем каждый шаг в sync_logs.
"""
import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import log
from app.core.security import decrypt_secret
from app.db.session import AsyncSessionLocal
from app.models import (
    OzonAccount,
    OzonAccountStatus,
    PriceHistory,
    Product,
    Stock,
    SyncLog,
    SyncStatus,
)
from app.services.ozon_client import OzonAPIError, OzonSellerClient
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, name="app.workers.tasks.sync_products.sync_all_products")
def sync_all_products(self) -> dict:
    """Запустить синхронизацию товаров по всем активным магазинам."""
    return asyncio.run(_sync_all_products_async())


async def _sync_all_products_async() -> dict:
    """Async реализация."""
    async with AsyncSessionLocal() as db:
        # Найти все активные магазины
        result = await db.execute(
            select(OzonAccount).where(
                OzonAccount.is_active.is_(True),
                OzonAccount.deleted_at.is_(None),
                OzonAccount.status == OzonAccountStatus.ACTIVE.value,
            )
        )
        accounts = result.scalars().all()

        log.info("sync_products_started", accounts_count=len(accounts))

        # Запускаем параллельно для всех магазинов
        results = await asyncio.gather(
            *[_sync_products_for_account(account.id) for account in accounts],
            return_exceptions=True,
        )

        success_count = sum(1 for r in results if isinstance(r, dict))
        failed_count = sum(1 for r in results if isinstance(r, Exception))

        log.info(
            "sync_products_finished",
            success=success_count,
            failed=failed_count,
        )

        return {
            "total": len(accounts),
            "success": success_count,
            "failed": failed_count,
        }


async def _sync_products_for_account(account_id: uuid.UUID) -> dict:
    """Синхронизировать товары одного магазина."""
    async with AsyncSessionLocal() as db:
        # Получаем магазин
        result = await db.execute(
            select(OzonAccount).where(OzonAccount.id == account_id)
        )
        account = result.scalar_one_or_none()

        if not account:
            log.error("account_not_found", account_id=str(account_id))
            return {"error": "account_not_found"}

        # Создаём запись в sync_logs
        sync_log = SyncLog(
            ozon_account_id=account.id,
            method="sync_products",
            status=SyncStatus.STARTED.value,
            started_at=datetime.now(UTC),
        )
        db.add(sync_log)
        await db.flush()

        started_at = datetime.now(UTC)
        records_processed = 0
        records_created = 0
        records_updated = 0
        error_message: str | None = None

        try:
            # Расшифровываем API ключи
            client_id = decrypt_secret(account.client_id_encrypted)
            api_key = decrypt_secret(account.api_key_encrypted)

            # Подключаемся к Озону
            async with OzonSellerClient(client_id, api_key) as client:
                # Тянем список товаров постранично
                last_id = ""
                while True:
                    response = await client.get_products(
                        limit=100, last_id=last_id
                    )
                    items = response.get("result", {}).get("items", [])

                    if not items:
                        break

                    # Сохраняем каждый товар
                    for item in items:
                        ozon_sku = item.get("product_id")
                        if not ozon_sku:
                            continue

                        # Ищем существующий
                        existing = await db.execute(
                            select(Product).where(
                                Product.ozon_account_id == account.id,
                                Product.ozon_sku == ozon_sku,
                            )
                        )
                        product = existing.scalar_one_or_none()

                        offer_id = item.get("offer_id", "")
                        name = item.get("name", "") or f"SKU {ozon_sku}"
                        is_archived = item.get("is_discounted", False)

                        if product:
                            # Обновляем
                            product.offer_id = offer_id
                            product.name = name
                            product.is_archived = is_archived
                            product.raw_data = item
                            records_updated += 1
                        else:
                            # Создаём
                            product = Product(
                                ozon_account_id=account.id,
                                ozon_sku=ozon_sku,
                                offer_id=offer_id,
                                name=name,
                                is_archived=is_archived,
                                raw_data=item,
                            )
                            db.add(product)
                            records_created += 1

                        records_processed += 1

                    last_id = response.get("result", {}).get("last_id", "")
                    if not last_id:
                        break

            await db.flush()

            # Обновляем статус магазина
            account.last_sync_at = datetime.now(UTC)
            account.last_sync_error = None
            account.status = OzonAccountStatus.ACTIVE.value

            # Финализируем sync_log
            sync_log.status = SyncStatus.SUCCESS.value
            sync_log.finished_at = datetime.now(UTC)
            sync_log.duration_ms = int(
                (sync_log.finished_at - started_at).total_seconds() * 1000
            )
            sync_log.records_processed = records_processed
            sync_log.records_created = records_created
            sync_log.records_updated = records_updated

            await db.commit()

            log.info(
                "products_synced",
                account_id=str(account.id),
                processed=records_processed,
                created=records_created,
                updated=records_updated,
            )

            return {
                "status": "success",
                "processed": records_processed,
                "created": records_created,
                "updated": records_updated,
            }

        except OzonAPIError as e:
            error_message = str(e)
            log.error(
                "ozon_api_error_in_sync",
                account_id=str(account.id),
                error=error_message,
            )
            account.status = OzonAccountStatus.ERROR.value
            account.last_sync_error = error_message[:500]

        except Exception as e:
            error_message = str(e)
            log.error(
                "sync_failed",
                account_id=str(account.id),
                error=error_message,
                exc_info=True,
            )

        # Финализируем при ошибке
        sync_log.status = SyncStatus.FAILED.value
        sync_log.finished_at = datetime.now(UTC)
        sync_log.duration_ms = int(
            (sync_log.finished_at - started_at).total_seconds() * 1000
        )
        sync_log.records_processed = records_processed
        sync_log.error_message = error_message
        await db.commit()

        return {"status": "failed", "error": error_message}


# Заглушки для других задач (доделаем позже)

@celery_app.task(name="app.workers.tasks.sync_products.sync_all_stocks")
def sync_all_stocks() -> dict:
    """TODO: реализовать синхронизацию остатков (snapshot в TimescaleDB)."""
    log.info("sync_stocks_called")
    return {"status": "todo"}


@celery_app.task(name="app.workers.tasks.sync_products.sync_all_prices")
def sync_all_prices() -> dict:
    """TODO: реализовать синхронизацию цен (snapshot в TimescaleDB)."""
    log.info("sync_prices_called")
    return {"status": "todo"}
