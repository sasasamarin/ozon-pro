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

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.core.security import decrypt_secret
from app.models import (
    OzonAccount,
    OzonAccountStatus,
    PendingCost,
    PriceHistory,
    Product,
    ProductCostHistory,
    Stock,
)
from app.models.cost import CostConfidence, CostSource
from app.services.ozon_client import OzonAPIError, OzonSellerClient
from app.services.warehouse_cluster import parse_warehouse_name
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import (
    get_active_accounts,
    load_extended_sku_map,
    load_offer_id_map,
    load_sku_map,
    run_celery_async,
    track_sync_log,
)


_ENRICH_BATCH = 100  # Размер чанка для /v3/product/info/list (limit Ozon = 1000, но 100 безопаснее по таймаутам)
_WAREHOUSE_PAGE_SIZE = 1000
_MAX_PAGES_WAREHOUSE = 100


def _clear_sync_error(account: OzonAccount) -> None:
    """Очищает last_sync_error и переводит статус в ACTIVE после успешного синка."""
    account.last_sync_error = None
    account.status = OzonAccountStatus.ACTIVE.value


# ============================================================
# TASK 4: sync_all_warehouse_stocks (per-warehouse breakdown)
# ============================================================


@celery_app.task(name="app.workers.tasks.sync_products.sync_all_warehouse_stocks")
def sync_all_warehouse_stocks(account_id: str | None = None) -> dict:
    """Per-warehouse остатки FBO через /v2/analytics/stock_on_warehouses.

    Дополняет sync_all_stocks (которая даёт только FBO/FBS aggregate) —
    добавляет warehouse_id + warehouse_name + cluster в hypertable `stocks`.
    """
    return run_celery_async(_sync_all_warehouse_stocks_async, account_id)


async def _sync_all_warehouse_stocks_async(
    SessionLocal: async_sessionmaker[AsyncSession],
    account_id: str | None = None,
) -> dict:
    async with SessionLocal() as db:
        if account_id:
            acc = (
                await db.execute(
                    select(OzonAccount).where(OzonAccount.id == uuid.UUID(account_id), OzonAccount.deleted_at.is_(None))
                )
            ).scalar_one_or_none()
            accounts = [acc] if acc else []
        else:
            accounts = await get_active_accounts(db)

    log.info("sync_warehouse_stocks_started", count=len(accounts))
    results = await asyncio.gather(
        *[_sync_warehouse_stocks_for_account(SessionLocal, a.id) for a in accounts],
        return_exceptions=True,
    )
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    return {"total": len(accounts), "success": success, "failed": len(results) - success}


async def _sync_warehouse_stocks_for_account(
    SessionLocal: async_sessionmaker[AsyncSession],
    account_id: uuid.UUID,
) -> dict:
    async with SessionLocal() as db:
        account = (
            await db.execute(select(OzonAccount).where(OzonAccount.id == account_id))
        ).scalar_one_or_none()
        if not account:
            return {"status": "failed", "error": "account_not_found"}

        try:
            async with track_sync_log(db, account.id, "sync_warehouse_stocks") as stats:
                # extended-map покрывает SKU вариантов складов (Ozon в analytics-
                # и warehouse-endpoint'ах возвращает variant SKU, не primary).
                sku_to_id = await load_extended_sku_map(db, account.id)
                offer_to_id = await load_offer_id_map(db, account.id)
                snapshot_at = datetime.now(UTC)

                client_id = decrypt_secret(account.client_id_encrypted)
                api_key = decrypt_secret(account.api_key_encrypted)

                rows: list[dict] = []
                async with OzonSellerClient(client_id, api_key) as client:
                    offset = 0
                    page = 0
                    while True:
                        page += 1
                        if page > _MAX_PAGES_WAREHOUSE:
                            log.error("pagination_runaway", method="warehouse_stocks", account=str(account_id))
                            break
                        response = await client.get_stock_on_warehouses(
                            limit=_WAREHOUSE_PAGE_SIZE, offset=offset, warehouse_type="ALL"
                        )
                        result = response.get("result") or {}
                        items = result.get("rows") or []
                        log.info("warehouse_stocks_page", account=str(account_id), page=page, items=len(items))
                        if not items:
                            break

                        for it in items:
                            sku = it.get("sku") or it.get("product_id")
                            offer = it.get("item_code")
                            product_id = None
                            if sku is not None:
                                product_id = sku_to_id.get(int(sku))
                            if product_id is None and offer:
                                product_id = offer_to_id.get(offer)
                            if not product_id:
                                continue
                            wh_name = it.get("warehouse_name") or "<aggregate>"
                            city, cluster = parse_warehouse_name(wh_name)
                            rows.append({
                                "time": snapshot_at,
                                "product_id": product_id,
                                # FBO_WH (per-warehouse) ≠ FBO (aggregate)
                                "warehouse_type": "FBO_WH",
                                "warehouse_name": wh_name,
                                "warehouse_id": int(it["warehouse_id"]) if it.get("warehouse_id") else None,
                                "free_to_sell": int(it.get("free_to_sell_amount", 0) or 0),
                                "reserved": int(it.get("reserved_amount", 0) or 0),
                                "in_transit": int(it.get("promised_amount", 0) or 0),
                                "cluster": cluster,
                            })
                            stats.processed += 1

                        if len(items) < _WAREHOUSE_PAGE_SIZE:
                            break
                        offset += len(items)

                if rows:
                    stmt = pg_insert(Stock).values(rows)
                    # PK теперь (time, product_id, warehouse_type, warehouse_name) —
                    # per-warehouse строки больше не теряются.
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["time", "product_id", "warehouse_type", "warehouse_name"],
                        set_={
                            col: stmt.excluded[col]
                            for col in ("free_to_sell", "reserved", "in_transit",
                                        "warehouse_id", "cluster")
                        },
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


# ============================================================
# TASK 1: sync_all_products
# ============================================================


@celery_app.task(bind=True, name="app.workers.tasks.sync_products.sync_all_products")
def sync_all_products(self, account_id: str | None = None) -> dict:
    """Синхронизация товаров. account_id='<uuid>' → один кабинет (Phase A)."""
    return run_celery_async(_sync_all_products_async, account_id)


async def _sync_all_products_async(
    SessionLocal: async_sessionmaker[AsyncSession],
    account_id: str | None = None,
) -> dict:
    async with SessionLocal() as db:
        q = select(OzonAccount).where(
            OzonAccount.is_active.is_(True),
            OzonAccount.deleted_at.is_(None),
        )
        if account_id:
            q = q.where(OzonAccount.id == uuid.UUID(account_id))
        result = await db.execute(q)
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


async def _pickup_pending_costs(db: AsyncSession, account: OzonAccount) -> int:
    """Переносит pending_costs в product_cost_history для появившихся товаров.

    Один user может владеть несколькими кабинетами; pending_costs привязаны к
    user_id, а не к account. Тянем все pending для company-owner этого кабинета
    и матчим к products *именно этого* account_id (чтобы не путать варианты
    между разными кабинетами).

    Возвращает количество перенесённых записей.
    """
    from datetime import datetime as _dt, timezone as _tz
    from app.models import User

    # user_id = первый юзер компании (owner)
    user_q = await db.execute(
        select(User.id)
        .where(User.company_id == account.company_id)
        .order_by(User.created_at)
        .limit(1)
    )
    user_id = user_q.scalar_one_or_none()
    if user_id is None:
        return 0

    # Все pending для этого юзера
    pendings = list(
        (
            await db.execute(
                select(PendingCost).where(PendingCost.user_id == user_id)
            )
        ).scalars().all()
    )
    if not pendings:
        return 0

    # Все products account'a с lower(offer_id) для быстрого map
    products = list(
        (
            await db.execute(
                select(Product).where(
                    Product.ozon_account_id == account.id,
                    Product.deleted_at.is_(None),
                )
            )
        ).scalars().all()
    )
    products_by_lower = {(p.offer_id or "").lower().strip(): p for p in products if p.offer_id}

    picked = 0
    effective_from = _dt(2026, 1, 1, 0, 0, 0, tzinfo=_tz.utc)

    for pending in pendings:
        matched = products_by_lower.get(pending.offer_id_lower)
        if not matched:
            continue

        # UPSERT в product_cost_history (PK = effective_from + product_id).
        # Если уже есть запись на 2026-01-01 (например, missing-stub) — UPDATE
        # её на estimated с реальной ценой. Иначе INSERT.
        existing = (
            await db.execute(
                select(ProductCostHistory).where(
                    ProductCostHistory.product_id == matched.id,
                    ProductCostHistory.effective_from == effective_from,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.purchase_price = pending.purchase_price
            existing.full_cost = pending.purchase_price
            existing.confidence = CostConfidence.ESTIMATED.value
            existing.source = CostSource.MANUAL.value
        else:
            db.add(
                ProductCostHistory(
                    effective_from=effective_from,
                    product_id=matched.id,
                    ozon_account_id=account.id,
                    user_id=user_id,
                    purchase_price=pending.purchase_price,
                    delivery_to_wh=0,
                    packaging=0,
                    other_costs=0,
                    full_cost=pending.purchase_price,
                    source=CostSource.MANUAL.value,
                    confidence=CostConfidence.ESTIMATED.value,
                )
            )
        matched.cost_price = pending.purchase_price

        # Удаляем pending
        await db.execute(
            delete(PendingCost).where(PendingCost.id == pending.id)
        )
        picked += 1

    return picked


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
                    # ---- ШАГ 1: /v3/product/list (visibility=ALL + ARCHIVED) ----
                    # Ozon-quirk: visibility=ALL НЕ возвращает архивные товары
                    # (проверено: home-кабинет дал 8 на ALL и 59 на ARCHIVED).
                    # Поэтому делаем ДВА прохода и объединяем.
                    offer_ids_to_enrich: list[str] = []
                    seen_skus: set[int] = set()

                    for vis in ("ALL", "ARCHIVED"):
                        last_id = ""
                        page = 0
                        while True:
                            page += 1
                            response = await client.get_products(
                                limit=100,
                                last_id=last_id,
                                filter_params={"visibility": vis},
                            )
                            items = response.get("result", {}).get("items", [])
                            log.info(
                                "products_page",
                                account=str(account.id),
                                visibility=vis,
                                page=page,
                                items=len(items),
                            )
                            if not items:
                                break

                            for item in items:
                                ozon_sku = item.get("product_id")
                                if not ozon_sku or ozon_sku in seen_skus:
                                    continue
                                seen_skus.add(ozon_sku)

                                existing = await db.execute(
                                    select(Product).where(
                                        Product.ozon_account_id == account.id,
                                        Product.ozon_sku == ozon_sku,
                                    )
                                )
                                product = existing.scalar_one_or_none()

                                offer_id = item.get("offer_id", "")
                                name_placeholder = f"SKU {ozon_sku}"
                                # ARCHIVED-проход всегда даёт архивные; на ALL
                                # архивных нет (см. quirk выше).
                                is_archived = (vis == "ARCHIVED") or bool(
                                    item.get("archived") or item.get("is_discounted")
                                )

                                if product:
                                    product.offer_id = offer_id
                                    product.is_archived = is_archived
                                    stats.updated += 1
                                else:
                                    product = Product(
                                        ozon_account_id=account.id,
                                        ozon_sku=ozon_sku,
                                        offer_id=offer_id,
                                        name=name_placeholder,
                                        is_archived=is_archived,
                                        raw_data=item,
                                    )
                                    db.add(product)
                                    stats.created += 1
                                stats.processed += 1

                                if offer_id:
                                    offer_ids_to_enrich.append(offer_id)

                            last_id = response.get("result", {}).get("last_id", "")
                            if not last_id:
                                break

                    # Сохраняем созданные Product, чтобы enrichment мог их найти.
                    await db.flush()

                    # ---- ШАГ 2: /v3/product/info/list — enrichment (имя, фото, баркод, категория) ----
                    if offer_ids_to_enrich:
                        for chunk_start in range(0, len(offer_ids_to_enrich), _ENRICH_BATCH):
                            chunk = offer_ids_to_enrich[chunk_start : chunk_start + _ENRICH_BATCH]
                            try:
                                info = await client.get_product_info(offer_ids=chunk)
                            except OzonAPIError as e:
                                log.warning("product_enrich_failed", chunk_size=len(chunk), err=str(e))
                                continue
                            detail_items = (
                                info.get("items")
                                or info.get("result", {}).get("items")
                                or []
                            )
                            for det in detail_items:
                                offer = det.get("offer_id")
                                if not offer:
                                    continue
                                row = await db.execute(
                                    select(Product).where(
                                        Product.ozon_account_id == account.id,
                                        Product.offer_id == offer,
                                    )
                                )
                                p = row.scalar_one_or_none()
                                if not p:
                                    continue
                                real_name = det.get("name")
                                if real_name and real_name.strip():
                                    p.name = real_name.strip()
                                barcode = det.get("barcode") or (
                                    (det.get("barcodes") or [None])[0]
                                )
                                if barcode:
                                    p.barcode = str(barcode)[:50]
                                category_id = det.get("category_id") or det.get("description_category_id")
                                if category_id:
                                    p.category_id = int(category_id)
                                if det.get("category_name"):
                                    p.category_name = det["category_name"][:255]
                                # raw_data из enrich — полнее, перезаписываем
                                p.raw_data = det

                # ---- ШАГ 3: подцепить pending_costs к свежесозданным продуктам ----
                # Если юзер импортировал CSV ДО появления товара на Ozon — в
                # pending_costs лежит (offer_id_lower, purchase_price). Берём
                # все pending_costs пользователя этого кабинета и матчим к
                # текущим products по lower(offer_id). Найденное → переносим
                # в product_cost_history, удаляем из pending_costs.
                picked = await _pickup_pending_costs(db, account)
                if picked:
                    log.info(
                        "pending_costs_picked",
                        account=str(account.id),
                        count=picked,
                    )

                account.last_sync_at = datetime.now(UTC)
                _clear_sync_error(account)
            await db.commit()
            return {"status": "success", "created": stats.created, "updated": stats.updated, "pending_picked": picked}
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
def sync_all_stocks(account_id: str | None = None) -> dict:
    return run_celery_async(_sync_all_stocks_async, account_id)


async def _sync_all_stocks_async(
    SessionLocal: async_sessionmaker[AsyncSession],
    account_id: str | None = None,
) -> dict:
    async with SessionLocal() as db:
        if account_id:
            acc = (
                await db.execute(
                    select(OzonAccount).where(OzonAccount.id == uuid.UUID(account_id), OzonAccount.deleted_at.is_(None))
                )
            ).scalar_one_or_none()
            accounts = [acc] if acc else []
        else:
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
                    # PK после миграции 0010 включает warehouse_name (иначе ORM identity-map
                    # склеивает per-warehouse строки). Без warehouse_name в ON CONFLICT
                    # запрос валится ProgrammingError → stocks ВООБЩЕ не пишутся
                    # с момента 0010 для тех кабинетов где приходит >1 строки на (time, sku, type).
                    # У warehouse_name дефолт '<aggregate>', null'ы не проблема.
                    for r in rows:
                        if r.get("warehouse_name") is None:
                            r["warehouse_name"] = "<aggregate>"
                    stmt = pg_insert(Stock).values(rows)
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=["time", "product_id", "warehouse_type", "warehouse_name"]
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
def sync_all_prices(account_id: str | None = None) -> dict:
    return run_celery_async(_sync_all_prices_async, account_id)


async def _sync_all_prices_async(
    SessionLocal: async_sessionmaker[AsyncSession],
    account_id: str | None = None,
) -> dict:
    async with SessionLocal() as db:
        if account_id:
            acc = (
                await db.execute(
                    select(OzonAccount).where(OzonAccount.id == uuid.UUID(account_id), OzonAccount.deleted_at.is_(None))
                )
            ).scalar_one_or_none()
            accounts = [acc] if acc else []
        else:
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
                            # Ozon шлёт СПП как 'marketing_seller_price', не 'marketing_price'.
                            # Старый код брал несуществующий ключ → у всех 81 товара NULL.
                            marketing_price = _to_decimal(price_node.get("marketing_seller_price"))
                            min_price = _to_decimal(price_node.get("min_price"))
                            price_index = (item.get("price_indexes") or {}).get(
                                "color_index"
                            ) or item.get("price_index")

                            # Точные комиссии и логистика Ozon per-товар (новое):
                            comm = item.get("commissions") or {}
                            volume_weight = _to_decimal(item.get("volume_weight"))
                            acquiring = _to_decimal(item.get("acquiring"))

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
                                # точные комиссии
                                if volume_weight is not None:
                                    product.volume_weight = volume_weight
                                if acquiring is not None:
                                    product.acquiring_amount = acquiring
                                if comm:
                                    product.commissions_raw = comm
                                    product.sales_percent_fbo = _to_decimal(comm.get("sales_percent_fbo"))
                                    product.sales_percent_fbs = _to_decimal(comm.get("sales_percent_fbs"))
                                    product.fbo_deliv_to_customer = _to_decimal(comm.get("fbo_deliv_to_customer_amount"))
                                    product.fbo_direct_flow_trans_min = _to_decimal(comm.get("fbo_direct_flow_trans_min_amount"))
                                    product.fbo_direct_flow_trans_max = _to_decimal(comm.get("fbo_direct_flow_trans_max_amount"))
                                    product.fbo_return_flow_amount = _to_decimal(comm.get("fbo_return_flow_amount"))
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


@celery_app.task(name="app.workers.tasks.sync_products.sync_full_account")
def sync_full_account(account_id: str) -> dict:
    """Запуск полной последовательной цепочки синхронизации для одного кабинета."""
    from app.workers.celery_app import celery_app

    log.info("sync_full_account_started", account_id=account_id)

    # Отправляем в очередь все задачи по очереди с фильтром по нашему кабинету
    # 1. Сначала товары (наполняем каталог)
    celery_app.send_task("app.workers.tasks.sync_products.sync_all_products", kwargs={"account_id": account_id})
    # 2. Текущие остатки
    celery_app.send_task("app.workers.tasks.sync_products.sync_all_stocks", kwargs={"account_id": account_id})
    # 3. Текущие цены и комиссии
    celery_app.send_task("app.workers.tasks.sync_products.sync_all_prices", kwargs={"account_id": account_id})
    # 4. Заказы за последние 30 дней (для первого наполнения)
    celery_app.send_task("app.workers.tasks.sync_orders.sync_all_orders",
                         kwargs={"account_id": account_id, "days_window": 30})
    # 5. Финансовые транзакции за последние 30 дней
    celery_app.send_task("app.workers.tasks.sync_finance.sync_all_transactions",
                         kwargs={"account_id": account_id, "days_window": 30})
    # 6. Аналитику воронки за последние 30 дней
    celery_app.send_task("app.workers.tasks.sync_analytics.sync_all_analytics",
                         kwargs={"account_id": account_id, "days_window": 30})

    return {"status": "success", "message": "Все задачи синхронизации успешно отправлены в очередь"}