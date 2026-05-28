"""
Синхронизация коммуникаций: отзывы, вопросы, чаты с покупателями.

- sync_all_reviews   — /v1/review/list   (требует premium_pro → skip)
- sync_all_questions — /v1/question/list (требует premium_pro → skip)
- sync_all_chats     — /v3/chat/list (+ history) — доступен всем тарифам
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
    Chat,
    ChatMessage,
    OzonAccount,
    OzonAccountStatus,
    OzonPremiumTier,
    Question,
    Review,
)
from app.services.ozon_client import OzonAPIError, OzonSellerClient
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import (
    get_active_accounts,
    load_sku_map,
    run_celery_async,
    tier_at_least,
    track_sync_log,
)


_MAX_PAGES = 1000


async def _pick_accounts(db: AsyncSession, account_id: str | None) -> list[OzonAccount]:
    if account_id:
        acc = (
            await db.execute(
                select(OzonAccount).where(OzonAccount.id == uuid.UUID(account_id), OzonAccount.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        return [acc] if acc else []
    return await get_active_accounts(db)


# ============================================================
# REVIEWS — premium_pro only
# ============================================================


@celery_app.task(name="app.workers.tasks.sync_communications.sync_all_reviews")
def sync_all_reviews(account_id: str | None = None) -> dict:
    return run_celery_async(_sync_all_reviews_async, account_id)


async def _sync_all_reviews_async(SessionLocal, account_id: str | None) -> dict:
    async with SessionLocal() as db:
        accounts = await _pick_accounts(db, account_id)
    eligible = [a for a in accounts if tier_at_least(a, OzonPremiumTier.PREMIUM_PRO)]
    log.info("sync_reviews_started", total=len(accounts), eligible=len(eligible))
    results = await asyncio.gather(
        *[_sync_reviews_for_account(SessionLocal, a.id) for a in eligible],
        return_exceptions=True,
    )
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    return {
        "total": len(eligible),
        "skipped_tier": len(accounts) - len(eligible),
        "success": success,
        "failed": len(results) - success,
    }


async def _sync_reviews_for_account(SessionLocal, account_id: uuid.UUID) -> dict:
    async with SessionLocal() as db:
        account = (await db.execute(select(OzonAccount).where(OzonAccount.id == account_id))).scalar_one_or_none()
        if not account:
            return {"status": "failed", "error": "account_not_found"}

        try:
            async with track_sync_log(db, account.id, "sync_reviews") as stats:
                sku_to_id = await load_sku_map(db, account.id)
                client_id = decrypt_secret(account.client_id_encrypted)
                api_key = decrypt_secret(account.api_key_encrypted)
                async with OzonSellerClient(client_id, api_key) as client:
                    last_id = ""
                    page = 0
                    while True:
                        page += 1
                        if page > _MAX_PAGES:
                            log.error("pagination_runaway", method="reviews", account=str(account_id))
                            break
                        response = await client.get_reviews(last_id=last_id, limit=100, status="ALL")
                        items = response.get("reviews") or response.get("result", {}).get("reviews") or []
                        log.info("reviews_page", account=str(account_id), page=page, items=len(items))
                        if not items:
                            break

                        bulk = []
                        for r in items:
                            rid = str(r.get("id") or r.get("review_id") or "")
                            if not rid:
                                continue
                            sku = r.get("sku") or r.get("product_id")
                            bulk.append({
                                "ozon_account_id": account.id,
                                "ozon_review_id": rid,
                                "ozon_sku": int(sku) if sku else None,
                                "product_id": sku_to_id.get(int(sku)) if sku else None,
                                "author_name": r.get("author_name") or (r.get("author") or {}).get("name"),
                                "rating": int(r.get("rating", 0) or 0) or None,
                                "text": r.get("text"),
                                "pluses": r.get("pluses"),
                                "minuses": r.get("minuses"),
                                "created_at_ozon": _parse_dt(r.get("created_at") or r.get("published_at")),
                                "status": r.get("status"),
                                "has_answer": bool(r.get("answered") or r.get("comments_amount", 0)),
                                "has_photos": bool(r.get("photos_amount") or r.get("media", {}).get("photos")),
                                "has_videos": bool(r.get("videos_amount") or r.get("media", {}).get("videos")),
                                "raw_data": r,
                            })
                            stats.processed += 1

                        if bulk:
                            stmt = pg_insert(Review).values(bulk)
                            stmt = stmt.on_conflict_do_update(
                                constraint="uq_reviews_account_review",
                                set_={c: stmt.excluded[c] for c in (
                                    "rating", "text", "pluses", "minuses", "status",
                                    "has_answer", "has_photos", "has_videos", "raw_data",
                                )},
                            )
                            await db.execute(stmt)
                            stats.updated += len(bulk)

                        last_id = response.get("last_id") or response.get("result", {}).get("last_id") or ""
                        if not last_id:
                            break

                account.last_sync_at = datetime.now(UTC)
                account.last_sync_error = None
                account.status = OzonAccountStatus.ACTIVE.value
            await db.commit()
            return {"status": "success", "rows": stats.processed}
        except OzonAPIError as e:
            account.status = OzonAccountStatus.ERROR.value
            account.last_sync_error = str(e)[:500]
            await db.commit()
            return {"status": "failed", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            return {"status": "failed", "error": str(e)}


# ============================================================
# QUESTIONS — premium_pro only
# ============================================================


@celery_app.task(name="app.workers.tasks.sync_communications.sync_all_questions")
def sync_all_questions(account_id: str | None = None) -> dict:
    return run_celery_async(_sync_all_questions_async, account_id)


async def _sync_all_questions_async(SessionLocal, account_id: str | None) -> dict:
    async with SessionLocal() as db:
        accounts = await _pick_accounts(db, account_id)
    eligible = [a for a in accounts if tier_at_least(a, OzonPremiumTier.PREMIUM_PRO)]
    log.info("sync_questions_started", total=len(accounts), eligible=len(eligible))
    results = await asyncio.gather(
        *[_sync_questions_for_account(SessionLocal, a.id) for a in eligible],
        return_exceptions=True,
    )
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    return {
        "total": len(eligible),
        "skipped_tier": len(accounts) - len(eligible),
        "success": success,
        "failed": len(results) - success,
    }


async def _sync_questions_for_account(SessionLocal, account_id: uuid.UUID) -> dict:
    async with SessionLocal() as db:
        account = (await db.execute(select(OzonAccount).where(OzonAccount.id == account_id))).scalar_one_or_none()
        if not account:
            return {"status": "failed", "error": "account_not_found"}

        try:
            async with track_sync_log(db, account.id, "sync_questions") as stats:
                sku_to_id = await load_sku_map(db, account.id)
                client_id = decrypt_secret(account.client_id_encrypted)
                api_key = decrypt_secret(account.api_key_encrypted)
                async with OzonSellerClient(client_id, api_key) as client:
                    last_id = ""
                    page = 0
                    while True:
                        page += 1
                        if page > _MAX_PAGES:
                            log.error("pagination_runaway", method="questions", account=str(account_id))
                            break
                        response = await client.get_questions(last_id=last_id, limit=100)
                        items = response.get("questions") or response.get("result", {}).get("questions") or []
                        log.info("questions_page", account=str(account_id), page=page, items=len(items))
                        if not items:
                            break

                        bulk = []
                        for q in items:
                            qid = str(q.get("id") or q.get("question_id") or "")
                            if not qid:
                                continue
                            sku = q.get("sku") or q.get("product_id")
                            bulk.append({
                                "ozon_account_id": account.id,
                                "ozon_question_id": qid,
                                "ozon_sku": int(sku) if sku else None,
                                "product_id": sku_to_id.get(int(sku)) if sku else None,
                                "author_name": q.get("author_name") or (q.get("author") or {}).get("name"),
                                "text": q.get("text") or q.get("question_text") or "",
                                "created_at_ozon": _parse_dt(q.get("created_at") or q.get("published_at")),
                                "answer_text": q.get("answer_text") or (q.get("answer") or {}).get("text"),
                                "answer_date": _parse_dt((q.get("answer") or {}).get("created_at")),
                                "status": q.get("status"),
                                "raw_data": q,
                            })
                            stats.processed += 1

                        if bulk:
                            stmt = pg_insert(Question).values(bulk)
                            stmt = stmt.on_conflict_do_update(
                                constraint="uq_questions_account_question",
                                set_={c: stmt.excluded[c] for c in (
                                    "text", "answer_text", "answer_date", "status", "raw_data",
                                )},
                            )
                            await db.execute(stmt)
                            stats.updated += len(bulk)

                        last_id = response.get("last_id") or response.get("result", {}).get("last_id") or ""
                        if not last_id:
                            break

                account.last_sync_at = datetime.now(UTC)
                account.last_sync_error = None
                account.status = OzonAccountStatus.ACTIVE.value
            await db.commit()
            return {"status": "success", "rows": stats.processed}
        except OzonAPIError as e:
            account.status = OzonAccountStatus.ERROR.value
            account.last_sync_error = str(e)[:500]
            await db.commit()
            return {"status": "failed", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            return {"status": "failed", "error": str(e)}


# ============================================================
# CHATS — все тарифы
# ============================================================


@celery_app.task(name="app.workers.tasks.sync_communications.sync_all_chats")
def sync_all_chats(account_id: str | None = None) -> dict:
    return run_celery_async(_sync_all_chats_async, account_id)


async def _sync_all_chats_async(SessionLocal, account_id: str | None) -> dict:
    async with SessionLocal() as db:
        accounts = await _pick_accounts(db, account_id)
    log.info("sync_chats_started", count=len(accounts))
    results = await asyncio.gather(
        *[_sync_chats_for_account(SessionLocal, a.id) for a in accounts],
        return_exceptions=True,
    )
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    return {"total": len(accounts), "success": success, "failed": len(results) - success}


async def _sync_chats_for_account(SessionLocal, account_id: uuid.UUID) -> dict:
    async with SessionLocal() as db:
        account = (await db.execute(select(OzonAccount).where(OzonAccount.id == account_id))).scalar_one_or_none()
        if not account:
            return {"status": "failed", "error": "account_not_found"}

        try:
            async with track_sync_log(db, account.id, "sync_chats") as stats:
                client_id = decrypt_secret(account.client_id_encrypted)
                api_key = decrypt_secret(account.api_key_encrypted)
                async with OzonSellerClient(client_id, api_key) as client:
                    cursor = ""
                    page = 0
                    while True:
                        page += 1
                        if page > _MAX_PAGES:
                            log.error("pagination_runaway", method="chats", account=str(account_id))
                            break
                        response = await client.get_chats(from_id=cursor, limit=100)
                        items = response.get("chats") or response.get("result", {}).get("chats") or []
                        log.info("chats_page", account=str(account_id), page=page, items=len(items))
                        if not items:
                            break

                        for c in items:
                            ozon_chat_id = c.get("chat_id") or c.get("id")
                            if not ozon_chat_id:
                                continue
                            await _upsert_chat(db, account_id=account.id, raw=c)
                            stats.processed += 1

                        cursor = response.get("cursor") or response.get("result", {}).get("cursor") or ""
                        if not cursor:
                            break

                # History сообщений — TODO в Phase 2.5. Сейчас только метаданные чатов.
                account.last_sync_at = datetime.now(UTC)
                account.last_sync_error = None
                account.status = OzonAccountStatus.ACTIVE.value
            await db.commit()
            return {"status": "success", "rows": stats.processed}
        except OzonAPIError as e:
            account.status = OzonAccountStatus.ERROR.value
            account.last_sync_error = str(e)[:500]
            await db.commit()
            return {"status": "failed", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            return {"status": "failed", "error": str(e)}


async def _upsert_chat(db: AsyncSession, *, account_id: uuid.UUID, raw: dict) -> None:
    ozon_chat_id = str(raw.get("chat_id") or raw.get("id") or "")
    if not ozon_chat_id:
        return
    payload = {
        "ozon_account_id": account_id,
        "user_id": None,  # backfill в будущей задаче
        "ozon_chat_id": ozon_chat_id,
        "posting_number": raw.get("posting_number") or (raw.get("posting") or {}).get("posting_number"),
        "customer_name": raw.get("customer_name") or (raw.get("customer") or {}).get("name"),
        "last_message_at": _parse_dt(raw.get("last_message_at") or raw.get("updated_at")),
        "unread_count": int(raw.get("unread_count", 0) or 0),
        "status": raw.get("status") or raw.get("chat_status"),
    }
    existing = await db.execute(
        select(Chat).where(
            Chat.ozon_account_id == account_id,
            Chat.ozon_chat_id == ozon_chat_id,
        )
    )
    row = existing.scalar_one_or_none()
    if row:
        for k, v in payload.items():
            setattr(row, k, v)
    else:
        db.add(Chat(**payload))


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
