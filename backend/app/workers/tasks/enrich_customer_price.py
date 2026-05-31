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
def enrich_customer_price(
    self,
    max_postings: int | None = None,
    account_id: str | None = None,
    since_date: str | None = None,
) -> dict:
    """
    Параметры:
      max_postings: всего за прогон
      account_id: конкретный кабинет (опционально)
      since_date: 'YYYY-MM-DD' — только заказы с этой даты (для приоритетного
                  бекфилла свежих дней)
    """
    return run_celery_async(
        _enrich_async,
        max_postings=max_postings,
        account_id=account_id,
        since_date=since_date,
    )


async def _enrich_async(
    SessionLocal,
    max_postings: int | None = None,
    account_id: str | None = None,
    since_date: str | None = None,
) -> dict:
    stats = {"processed": 0, "updated": 0, "skipped": 0, "errors": 0, "started_at": datetime.now(UTC).isoformat()}

    async with SessionLocal() as db:
        accounts_query = select(OzonAccount).where(OzonAccount.is_active.is_(True))
        if account_id:
            accounts_query = accounts_query.where(OzonAccount.id == uuid.UUID(account_id))
        accounts = (await db.execute(accounts_query)).scalars().all()
        log.info("enrich_customer_price_start", accounts=len(accounts), max_postings=max_postings)

        for ac in accounts:
            await _enrich_account(db, ac, stats, max_postings=max_postings, since_date=since_date)

    stats["finished_at"] = datetime.now(UTC).isoformat()
    log.info("enrich_customer_price_done", **stats)
    return stats


async def _enrich_account(
    db: AsyncSession,
    account: OzonAccount,
    stats: dict,
    max_postings: int | None,
    since_date: str | None = None,
) -> None:
    """Обогащаем postings одного кабинета. ORDER BY order_created_at DESC —
    свежие первыми. since_date='YYYY-MM-DD' — фильтр для приоритетного бекфилла.
    """
    limit_sql = f"LIMIT {int(max_postings)}" if max_postings else ""
    params: dict = {"acc": str(account.id)}
    since_clause = ""
    if since_date:
        # asyncpg ждёт datetime, не строку — конвертим явно
        from datetime import datetime as _dt
        since_clause = "AND o.order_created_at >= :since"
        params["since"] = _dt.fromisoformat(f"{since_date}T00:00:00+00:00")
    rows = (await db.execute(text(f"""
        SELECT o.posting_number, MAX(o.order_created_at) max_dt
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        WHERE o.ozon_account_id = :acc
          AND o.order_type = 'fbo'
          AND oi.customer_price IS NULL
          {since_clause}
        GROUP BY o.posting_number
        ORDER BY MAX(o.order_created_at) DESC
        {limit_sql}
    """), params)).all()
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
                    # Возвращает {ozon_sku: customer_price} — для матчинга per-item.
                    # Раньше брали products[0].customer_price и писали ВСЕМ позициям
                    # посту → если в посту >1 товара с разными ценами, Жирафу
                    # присваивалось значение чужого товара (видели 81419, 86946).
                    sku_to_cp = await _fetch_customer_prices_by_sku(client, p_num)
                    if not sku_to_cp:
                        stats["skipped"] += 1
                        continue
                    rows_updated = 0
                    for sku, cp in sku_to_cp.items():
                        res = await db.execute(text("""
                            UPDATE order_items oi
                            SET customer_price = :cp
                            FROM orders o
                            WHERE oi.order_id = o.id
                              AND o.posting_number = :p
                              AND oi.ozon_sku = :sku
                              AND oi.customer_price IS NULL
                        """), {"cp": cp, "p": p_num, "sku": sku})
                        rows_updated += res.rowcount
                    if rows_updated > 0:
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


async def _fetch_customer_prices_by_sku(client: OzonSellerClient, posting_number: str) -> dict[int, float]:
    """Дёргаем /v2/posting/fbo/get → возвращаем {ozon_sku: customer_price}
    для КАЖДОГО товара в посту. Матчим в БД по sku, чтобы при posting'е с
    несколькими разными товарами каждой позиции писалась ЕЁ цена покупателя.
    """
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
    out: dict[int, float] = {}
    for fp in products:
        sku = fp.get("product_id")
        cp = fp.get("customer_price")
        if sku is None or cp is None:
            continue
        try:
            out[int(sku)] = float(cp)
        except (TypeError, ValueError):
            continue
    return out
