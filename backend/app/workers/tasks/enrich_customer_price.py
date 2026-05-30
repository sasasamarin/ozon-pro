"""
Backfill + ongoing enrichment `order_items.customer_price`.

customer_price (= «оплачено покупателем» с СПП/Ozon-Картой) отдаётся ТОЛЬКО
в /v2/posting/fbo/get (per-posting), не в /list. Поэтому делаем отдельным
проходом после основного sync_orders.

Используется и для backfill истории (29k заказов), и для ongoing обогащения
новых postings.

Throttle: Ozon FBO API лимит 100 запросов/мин на эндпоинт. Берём батч 50,
sleep 30s между батчами = 100 RPM с запасом.

Прогресс пишется в log + Marker (для UI индикатора в Settings).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import structlog
from celery import shared_task
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret
from app.models import OrderItem, OzonAccount
from app.services.ozon_client import OzonSellerClient
from app.workers.tasks._helpers import run_celery_async

log = structlog.get_logger()
UTC = timezone.utc

_BATCH = 50              # сколько postings обогащаем одним проходом без sleep
_BATCH_SLEEP_SEC = 30    # пауза между батчами (для 100 RPM throttle)
_MAX_RETRIES = 3


@shared_task(name="enrich_customer_price", bind=True)
def enrich_customer_price(self, max_postings: int | None = None, account_id: str | None = None) -> dict:
    """
    Сall: enrich_customer_price.delay(max_postings=29000)  # backfill всё
          enrich_customer_price.delay(max_postings=500)    # ongoing хвост
    """
    return run_celery_async(_enrich_async, max_postings=max_postings, account_id=account_id)


async def _enrich_async(SessionLocal, max_postings: int | None = None, account_id: str | None = None) -> dict:
    stats = {"processed": 0, "updated": 0, "skipped": 0, "errors": 0, "started_at": datetime.now(UTC).isoformat()}

    async with SessionLocal() as db:
        accounts_query = select(OzonAccount).where(OzonAccount.is_active.is_(True))
        if account_id:
            accounts_query = accounts_query.where(OzonAccount.id == uuid.UUID(account_id))
        accounts = (await db.execute(accounts_query)).scalars().all()
        log.info("enrich_customer_price_start", accounts=len(accounts), max_postings=max_postings)

        for ac in accounts:
            await _enrich_account(db, ac, stats, max_postings=max_postings)

    stats["finished_at"] = datetime.now(UTC).isoformat()
    log.info("enrich_customer_price_done", **stats)
    return stats


async def _enrich_account(
    db: AsyncSession,
    account: OzonAccount,
    stats: dict,
    max_postings: int | None,
) -> None:
    """Обогащаем postings одного кабинета."""
    # Берём posting_number'ы где customer_price пуст хотя бы у одного OrderItem
    # И сам order — FBO (там есть customer_price; FBS не отдаёт)
    limit_sql = f"LIMIT {int(max_postings)}" if max_postings else ""
    rows = (await db.execute(text(f"""
        SELECT DISTINCT o.posting_number
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        WHERE o.ozon_account_id = :acc
          AND o.order_type = 'fbo'
          AND oi.customer_price IS NULL
        ORDER BY o.posting_number DESC
        {limit_sql}
    """), {"acc": str(account.id)})).all()
    postings = [r[0] for r in rows]
    if not postings:
        log.info("enrich_account_nothing_to_do", account=str(account.id))
        return

    log.info("enrich_account_start", account=str(account.id), postings=len(postings))

    cid = decrypt_secret(account.client_id_encrypted)
    apk = decrypt_secret(account.api_key_encrypted)

    async with OzonSellerClient(cid, apk) as client:
        for batch_idx, batch_start in enumerate(range(0, len(postings), _BATCH)):
            batch = postings[batch_start:batch_start + _BATCH]
            for p_num in batch:
                try:
                    customer_price = await _fetch_customer_price(client, p_num)
                    if customer_price is None:
                        stats["skipped"] += 1
                        continue
                    res = await db.execute(text("""
                        UPDATE order_items
                        SET customer_price = :cp
                        WHERE order_id IN (SELECT id FROM orders WHERE posting_number = :p)
                          AND customer_price IS NULL
                    """), {"cp": customer_price, "p": p_num})
                    if res.rowcount > 0:
                        stats["updated"] += 1
                    stats["processed"] += 1
                except Exception:
                    log.exception("enrich_posting_failed", posting=p_num)
                    stats["errors"] += 1
                    stats["processed"] += 1
                    continue
            await db.commit()
            log.info(
                "enrich_batch_done",
                account=str(account.id),
                batch=batch_idx + 1,
                total_batches=(len(postings) + _BATCH - 1) // _BATCH,
                processed=stats["processed"],
                updated=stats["updated"],
                errors=stats["errors"],
            )
            # throttle между батчами
            if batch_start + _BATCH < len(postings):
                await asyncio.sleep(_BATCH_SLEEP_SEC)


async def _fetch_customer_price(client: OzonSellerClient, posting_number: str) -> float | None:
    """Дёргаем /v2/posting/fbo/get → достаём customer_price первого товара."""
    r = await client._request(
        "POST",
        "/v2/posting/fbo/get",
        json={
            "posting_number": posting_number,
            "with": {"financial_data": True, "analytics_data": False},
        },
    )
    result = r.get("result") or {}
    fd = result.get("financial_data") or {}
    products = fd.get("products") or []
    if not products:
        return None
    cp = products[0].get("customer_price")
    if cp is None:
        return None
    try:
        return float(cp)
    except (TypeError, ValueError):
        return None
