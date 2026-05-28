"""
Синхронизация товаров, остатков и цен с Ozon Seller API.

- sync_all_products — список товаров (upsert в products)
- sync_all_stocks   — снимки остатков (insert в stocks hypertable)
- sync_all_prices   — снимки цен (insert в price_history hypertable) +
                       обновляет текущие цены в products

Все 3 таска запускаются через `run_celery_async()` — она создаёт фреш
AsyncEngine на каждый вызов (Celery prefork + asyncio.run несовместимы
со static-engine'ом из db.session).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.core.security import decrypt_secret
from app.models import (
    OzonAccount,
    OzonAccountStatus,
    PriceHistory,
    Product,
    Stock,
)
from app.services.ozon_client import OzonAPIError, OzonSellerClient
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import (
    get_active_accounts,
    load_sku_map,
    run_celery_async,
    track_sync_log,
)


def _clear_sync_error(account: OzonAccount) -> None:
    """Очищает last_sync_error и переводит статус в ACTIVE после успешного синка."""
    account.last_sync_error = None
    account.status = OzonAccountStatus.ACTIVE.value


# ============================================================
# TASK 1: sync_all_products
# ============================================================


@celery_app.task(bind=True, name="app.workers.tasks.sync_products.sync_all_products")
def sync_all_products(self) -> dict:
    """Запустить синхронизацию товаров по всем активным магазинам."""
    return run_celery_async(_sync_all_products_async)


async def _sync_all_products_async(
    SessionLocal: async_sessionmaker[AsyncSession],
) -> dict:
    async with SessionLocal() as db:
        result = await db.execute(
            select(OzonAccount).where(
                OzonAccount.is_active.is_(True),
                OzonAccount.deleted_at.is_(None),
            )
        )
        accounts = list(result.scalars().all())

    log.info("sync_products_started", accounts_count=len(accounts))
    results = await asyncio.gather(
        *[_sync_products_for_account(SessionLocal, account.id) for account in accounts],
        return_exceptions=True,
    )

    success_count = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    failed_count = len(results) - success_count
    log.info("sync_products_finished", success=success_count, failed=failed_count)
    return {"total": len(accounts), "success": success_count, "failed": failed_count}


async def _sync_products_for_account(
    SessionLocal: async_sessionmaker[AsyncSession], account_id: uuid.UUID
) -> dict:
    async with SessionLocal() as db:
        account = (
            await db.execute(select(OzonAccount).where(OzonAccount.id == account_id))
        ).scalar_one_or_none()
        if not account:
            return {"status": "failed", "error": "account_not_found"}

        try:
            async with track_sync_log(db, account.id, "sync_products") as stats:
                client_id = decrypt_secret(account.client_id_encrypted)
                api_key = decrypt_secret(account.api_key_encrypted)
                async with OzonSellerClient(client_id, api_key) as client:
                    last_id = ""
                    while True:
                        response = await client.get_products(limit=100, last_id=last_id)
                        items = response.get("result", {}).get("items", [])
                        if not items:
                            break

                        for item in items:
                            ozon_sku = item.get("product_id")
                            if not ozon_sku:
                                continue

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
                                product.offer_id = offer_id
                                product.name = name
                                product.is_archived = is_archived
                                product.raw_data = item
                                stats.updated += 1
                            else:
                                product = Product(
                                    ozon_account_id=account.id,
                                    ozon_sku=ozon_sku,
                                    offer_id=offer_id,
                                    name=name,
                                    is_archived=is_archived,
                                    raw_data=item,
                                )
                                db.add(product)
                                stats.created += 1
                            stats.processed += 1

                        last_id = response.get("result", {}).get("last_id", "")
                        if not last_id:
                            break

                account.last_sync_at = datetime.now(UTC)
                _clear_sync_error(account)
            await db.commit()
            return {"status": "success", "created": stats.created, "updated": stats.updated}
        except OzonAPIError as e:
            account.status = OzonAccountStatus.ERROR.value
            account.last_sync_error = str(e)[:500]
            await db.commit()
            return {"status": "failed", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            return {"status": "failed", "error": str(e)}


# ============================================================
# TASK 2: sync_all_stocks
# ============================================================


@celery_app.task(name="app.workers.tasks.sync_products.sync_all_stocks")
def sync_all_stocks() -> dict:
    return run_celery_async(_sync_all_stocks_async)


async def _sync_all_stocks_async(
    SessionLocal: async_sessionmaker[AsyncSession],
) -> dict:
    async with SessionLocal() as db:
        accounts = await get_active_accounts(db)

    log.info("sync_stocks_started", accounts_count=len(accounts))
    results = await asyncio.gather(
        *[_sync_stocks_for_account(SessionLocal, acc.id) for acc in accounts],
        return_exceptions=True,
    )
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    return {"total": len(accounts), "success": success, "failed": len(results) - success}


async def _sync_stocks_for_account(
    SessionLocal: async_sessionmaker[AsyncSession], account_id: uuid.UUID
) -> dict:
    async with SessionLocal() as db:
        account = (
            await db.execute(select(OzonAccount).where(OzonAccount.id == account_id))
        ).scalar_one_or_none()
        if not account:
            return {"status": "failed", "error": "account_not_found"}

        try:
            async with track_sync_log(db, account.id, "sync_stocks") as stats:
                sku_to_id = await load_sku_map(db, account.id)
                snapshot_at = datetime.now(UTC)

                client_id = decrypt_secret(account.client_id_encrypted)
                api_key = decrypt_secret(account.api_key_encrypted)

                rows: list[dict] = []

                async with OzonSellerClient(client_id, api_key) as client:
                    cursor = ""
                    while True:
                        response = await client.get_stocks(limit=100, cursor=cursor)
                        items = response.get("items") or response.get("result", {}).get("items", [])
                        if not items:
                            break

                        for item in items:
                            ozon_sku = item.get("product_id") or item.get("sku")
                            product_id = sku_to_id.get(ozon_sku)
                            if not product_id:
                                continue

                            for st in item.get("stocks", []):
                                rows.append(_stock_row(
                                    snapshot_at=snapshot_at,
                                    product_id=product_id,
                                    raw=st,
                                ))
                                stats.processed += 1

                        cursor = response.get("cursor", "")
                        if not cursor:
                            break

                if rows:
                    stmt = pg_insert(Stock).values(rows)
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=["time", "product_id", "warehouse_type"]
                    )
                    await db.execute(stmt)
                    stats.created += len(rows)

                account.last_sync_at = snapshot_at
                _clear_sync_error(account)
            await db.commit()
            return {"status": "success", "rows": stats.created}
        except OzonAPIError as e:
            account.status = OzonAccountStatus.ERROR.value
            account.last_sync_error = str(e)[:500]
            await db.commit()
            return {"status": "failed", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            return {"status": "failed", "error": str(e)}


def _stock_row(
    *, snapshot_at: datetime, product_id: uuid.UUID, raw: dict
) -> dict:
    warehouse_type = (raw.get("type") or "FBO").upper()
    return {
        "time": snapshot_at,
        "product_id": product_id,
        "warehouse_type": warehouse_type,
        "warehouse_name": raw.get("warehouse_name") or raw.get("cluster"),
        "warehouse_id": raw.get("warehouse_id"),
        "free_to_sell": int(raw.get("present", raw.get("free_to_sell_amount", 0)) or 0),
        "reserved": int(raw.get("reserved", 0) or 0),
        "in_transit": int(raw.get("in_transit_qty", raw.get("in_transit", 0)) or 0),
        "cluster": raw.get("cluster") or raw.get("cluster_name"),
    }


# ============================================================
# TASK 3: sync_all_prices
# ============================================================


@celery_app.task(name="app.workers.tasks.sync_products.sync_all_prices")
def sync_all_prices() -> dict:
    return run_celery_async(_sync_all_prices_async)


async def _sync_all_prices_async(
    SessionLocal: async_sessionmaker[AsyncSession],
) -> dict:
    async with SessionLocal() as db:
        accounts = await get_active_accounts(db)

    log.info("sync_prices_started", accounts_count=len(accounts))
    results = await asyncio.gather(
        *[_sync_prices_for_account(SessionLocal, acc.id) for acc in accounts],
        return_exceptions=True,
    )
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    return {"total": len(accounts), "success": success, "failed": len(results) - success}


async def _sync_prices_for_account(
    SessionLocal: async_sessionmaker[AsyncSession], account_id: uuid.UUID
) -> dict:
    async with SessionLocal() as db:
        account = (
            await db.execute(select(OzonAccount).where(OzonAccount.id == account_id))
        ).scalar_one_or_none()
        if not account:
            return {"status": "failed", "error": "account_not_found"}

        try:
            async with track_sync_log(db, account.id, "sync_prices") as stats:
                sku_to_id = await load_sku_map(db, account.id)
                snapshot_at = datetime.now(UTC)

                client_id = decrypt_secret(account.client_id_encrypted)
                api_key = decrypt_secret(account.api_key_encrypted)

                rows: list[dict] = []

                async with OzonSellerClient(client_id, api_key) as client:
                    cursor = ""
                    while True:
                        response = await client.get_product_prices(limit=100, cursor=cursor)
                        items = response.get("items") or response.get("result", {}).get("items", [])
                        if not items:
                            break

                        for item in items:
                            ozon_sku = item.get("product_id") or item.get("sku")
                            product_id = sku_to_id.get(ozon_sku)
                            if not product_id:
                                continue

                            price_node = item.get("price", {})
                            price = _to_decimal(price_node.get("price"))
                            old_price = _to_decimal(price_node.get("old_price"))
                            marketing_price = _to_decimal(price_node.get("marketing_price"))
                            min_price = _to_decimal(price_node.get("min_price"))
                            price_index = (item.get("price_indexes") or {}).get(
                                "color_index"
                            ) or item.get("price_index")

                            if price is not None:
                                rows.append({
                                    "time": snapshot_at,
                                    "product_id": product_id,
                                    "price": price,
                                    "marketing_price": marketing_price,
                                    "old_price": old_price,
                                    "price_index": price_index,
                                })

                            existing = await db.execute(
                                select(Product).where(Product.id == product_id)
                            )
                            product = existing.scalar_one_or_none()
                            if product:
                                product.current_price = price
                                product.old_price = old_price
                                product.marketing_price = marketing_price
                                product.min_price = min_price
                                product.price_index = price_index
                                stats.updated += 1
                            stats.processed += 1

                        cursor = response.get("cursor", "")
                        if not cursor:
                            break

                if rows:
                    stmt = pg_insert(PriceHistory).values(rows)
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=["time", "product_id"]
                    )
                    await db.execute(stmt)
                    stats.created += len(rows)

                account.last_sync_at = snapshot_at
                _clear_sync_error(account)
            await db.commit()
            return {"status": "success", "rows": stats.created}
        except OzonAPIError as e:
            account.status = OzonAccountStatus.ERROR.value
            account.last_sync_error = str(e)[:500]
            await db.commit()
            return {"status": "failed", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            return {"status": "failed", "error": str(e)}


def _to_decimal(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
