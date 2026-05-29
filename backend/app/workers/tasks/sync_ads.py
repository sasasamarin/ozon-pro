"""
Синхронизация рекламы (Ozon Performance API).

- sync_all_ad_campaigns — список кампаний (upsert в ad_campaigns)
- sync_all_ad_statistics — ежедневная статистика по кампаниям
  (insert в ad_statistics hypertable, idempotent через ON CONFLICT)

Если у кабинета НЕ настроены PA-ключи (perf_client_id_encrypted is NULL) —
тихо скипаем этот кабинет, не ломаемся.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date as date_cls, datetime, timedelta
from typing import Any

# Хелпер: NIL UUID для агрегатов «кампания целиком, без разбивки на товары».
# product_id входит в PK ad_statistics, поэтому для агрегата нужен какой-то
# валидный, но определённо «не-товарный» UUID.
NIL_UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.models import AdCampaign, AdStatistics, OzonAccount
from app.services.ozon_client import OzonAPIError
from app.services.ozon_perf_client import (
    OzonPerformanceClient,
    OzonPerfNotConfigured,
)
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import (
    get_active_accounts,
    run_celery_async,
    track_sync_log,
)


# ============================================================
# TASK 1: sync_all_ad_campaigns
# ============================================================


@celery_app.task(name="app.workers.tasks.sync_ads.sync_all_ad_campaigns")
def sync_all_ad_campaigns(account_id: str | None = None) -> dict:
    """Список рекламных кампаний по всем активным магазинам с подключённым PA."""
    return run_celery_async(_sync_all_ad_campaigns_async, account_id)


async def _sync_all_ad_campaigns_async(
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

    eligible = [a for a in accounts if a.perf_client_id_encrypted]
    log.info(
        "sync_ad_campaigns_started",
        accounts_total=len(accounts),
        accounts_with_pa=len(eligible),
    )
    results = await asyncio.gather(
        *[_sync_ad_campaigns_for_account(SessionLocal, a.id) for a in eligible],
        return_exceptions=True,
    )
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    return {
        "total": len(eligible),
        "skipped_no_pa": len(accounts) - len(eligible),
        "success": success,
        "failed": len(results) - success,
    }


async def _sync_ad_campaigns_for_account(
    SessionLocal: async_sessionmaker[AsyncSession], account_id: uuid.UUID
) -> dict:
    async with SessionLocal() as db:
        account = (
            await db.execute(select(OzonAccount).where(OzonAccount.id == account_id))
        ).scalar_one_or_none()
        if not account:
            return {"status": "failed", "error": "account_not_found"}

        try:
            async with track_sync_log(db, account.id, "sync_ad_campaigns") as stats:
                async with OzonPerformanceClient(account, db) as client:
                    raw_campaigns = await client.get_campaigns()

                for raw in raw_campaigns:
                    await _upsert_campaign(db, account_id=account.id, raw=raw)
                    stats.processed += 1
            await db.commit()
            return {"status": "success", "count": stats.processed}
        except OzonPerfNotConfigured:
            await db.rollback()
            return {"status": "skipped", "reason": "no_perf_keys"}
        except OzonAPIError as e:
            await db.rollback()
            return {"status": "failed", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            log.exception("sync_failed_unexpected", account_id=str(account_id))
            return {"status": "failed", "error": str(e)}


_STATE_MAP = {
    "CAMPAIGN_STATE_RUNNING": "running",
    "CAMPAIGN_STATE_PLANNED": "planned",
    "CAMPAIGN_STATE_INACTIVE": "paused",
    "CAMPAIGN_STATE_PAUSED": "paused",
    "CAMPAIGN_STATE_STOPPED": "paused",
    "CAMPAIGN_STATE_FINISHED": "finished",
    "CAMPAIGN_STATE_ARCHIVED": "archived",
}

_TYPE_MAP = {
    "SKU": "sku",
    "SEARCH_PROMO": "search_promo",
    "BANNER": "banner",
    "BRAND_SHELF": "brand_shelf",
    "PREMIUM": "brand_shelf",
    "REF_VK": "ref_vk",
}

# Модель оплаты по advObjectType — нужно для расчёта ROMI и графика «Реклама→Заказы».
_PAYMENT_MAP = {
    "SKU": "PER_CLICK",          # трафареты CPC
    "SEARCH_PROMO": "PER_ORDER", # «продвижение в поиске» — CPA
    "BANNER": "CPM",             # баннеры за показы
    "BRAND_SHELF": "FIXED",      # брендовая полка фикс
    "PREMIUM": "FIXED",
    "REF_VK": "PER_CLICK",
}


def _norm_state(raw_state: str | None) -> str:
    s = (raw_state or "").upper()
    return _STATE_MAP.get(s, "unknown")


def _norm_type(raw_type: str | None) -> str:
    t = (raw_type or "").upper()
    return _TYPE_MAP.get(t, "unknown")


def _payment_model(raw_type: str | None) -> str:
    t = (raw_type or "").upper()
    return _PAYMENT_MAP.get(t, "PER_CLICK")


async def _upsert_campaign(
    db: AsyncSession, *, account_id: uuid.UUID, raw: dict
) -> None:
    ozon_campaign_id = str(raw.get("id") or raw.get("campaignId") or "")
    if not ozon_campaign_id:
        return

    raw_type = raw.get("advObjectType") or raw.get("type")
    enriched_raw = dict(raw)
    enriched_raw["__payment_model"] = _payment_model(raw_type)

    payload: dict[str, Any] = {
        "ozon_account_id": account_id,
        "ozon_campaign_id": ozon_campaign_id,
        "title": (raw.get("title") or raw.get("name") or f"Кампания {ozon_campaign_id}")[:255],
        "campaign_type": _norm_type(raw_type),
        "state": _norm_state(raw.get("state")),
        "from_date": _parse_date(raw.get("fromDate")),
        "to_date": _parse_date(raw.get("toDate")),
        "daily_budget": _to_float(raw.get("dailyBudget")),
        "weekly_budget": _to_float(raw.get("weeklyBudget")),
        "budget": _to_float(raw.get("budget")),
        "raw_data": enriched_raw,
    }

    existing = await db.execute(
        select(AdCampaign).where(
            AdCampaign.ozon_account_id == account_id,
            AdCampaign.ozon_campaign_id == ozon_campaign_id,
        )
    )
    campaign = existing.scalar_one_or_none()
    if campaign:
        for k, v in payload.items():
            setattr(campaign, k, v)
    else:
        db.add(AdCampaign(**payload))


# ============================================================
# TASK 2: sync_all_ad_statistics
# ============================================================


@celery_app.task(name="app.workers.tasks.sync_ads.sync_all_ad_statistics")
def sync_all_ad_statistics(
    days_window: int = 3,
    date_from: str | None = None,
    account_id: str | None = None,
) -> dict:
    """Дневная статистика рекламы. cron → days_window=3, ручной backfill → date_from."""
    return run_celery_async(_sync_all_ad_statistics_async, days_window, date_from, account_id)


async def _sync_all_ad_statistics_async(
    SessionLocal: async_sessionmaker[AsyncSession],
    days_window: int,
    date_from: str | None = None,
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

    eligible = [a for a in accounts if a.perf_client_id_encrypted]
    log.info(
        "sync_ad_statistics_started",
        accounts_with_pa=len(eligible),
        days=days_window,
        date_from=date_from,
    )
    results = await asyncio.gather(
        *[_sync_ad_statistics_for_account(SessionLocal, a.id, days_window, date_from) for a in eligible],
        return_exceptions=True,
    )
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    return {
        "total": len(eligible),
        "skipped_no_pa": len(accounts) - len(eligible),
        "success": success,
        "failed": len(results) - success,
    }


async def _sync_ad_statistics_for_account(
    SessionLocal: async_sessionmaker[AsyncSession],
    account_id: uuid.UUID,
    days_window: int,
    date_from_iso: str | None = None,
) -> dict:
    async with SessionLocal() as db:
        account = (
            await db.execute(select(OzonAccount).where(OzonAccount.id == account_id))
        ).scalar_one_or_none()
        if not account:
            return {"status": "failed", "error": "account_not_found"}

        # Сначала находим список активных кампаний в нашей БД для этого аккаунта.
        # Если кампаний нет — sync_all_ad_campaigns ещё не запускался, скипаем.
        existing_campaigns = (
            await db.execute(
                select(AdCampaign.ozon_campaign_id).where(
                    AdCampaign.ozon_account_id == account_id
                )
            )
        ).scalars().all()

        if not existing_campaigns:
            return {"status": "skipped", "reason": "no_campaigns_yet"}

        date_to = datetime.now(UTC).date()
        if date_from_iso:
            try:
                date_from = date_cls.fromisoformat(date_from_iso[:10])
            except ValueError:
                return {"status": "failed", "error": f"invalid date_from={date_from_iso}"}
        else:
            date_from = date_to - timedelta(days=days_window)

        try:
            async with track_sync_log(db, account.id, "sync_ad_statistics") as stats:
                async with OzonPerformanceClient(account, db) as client:
                    response = await client.get_daily_stats(
                        date_from=date_from.isoformat(),
                        date_to=date_to.isoformat(),
                        campaign_ids=list(existing_campaigns),
                    )

                rows = _flatten_daily_stats(
                    response,
                    account_id=account_id,
                    fallback_campaigns=list(existing_campaigns),
                )

                if rows:
                    stmt = pg_insert(AdStatistics).values(rows)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["date", "ozon_campaign_id", "product_id"],
                        set_={
                            col: stmt.excluded[col]
                            for col in (
                                "impressions", "clicks", "orders", "revenue",
                                "spend", "ctr", "drr", "roas", "avg_bid", "raw_data",
                            )
                        },
                    )
                    await db.execute(stmt)
                    stats.processed = len(rows)
                    stats.updated = len(rows)
            await db.commit()
            return {"status": "success", "rows": stats.processed}
        except OzonPerfNotConfigured:
            await db.rollback()
            return {"status": "skipped", "reason": "no_perf_keys"}
        except OzonAPIError as e:
            await db.rollback()
            return {"status": "failed", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            log.exception("sync_failed_unexpected", account_id=str(account_id))
            return {"status": "failed", "error": str(e)}


def _flatten_daily_stats(
    response: dict,
    *,
    account_id: uuid.UUID,
    fallback_campaigns: list[str],
) -> list[dict]:
    """
    Ozon Performance отдаёт по-разному в зависимости от типа кампании.
    Берём максимально широкий набор полей; чего не нашли — оставляем 0/None.

    Ожидаемые формы:
    - {"rows": [{"date","campaignId","views","clicks","ordered","revenue","moneySpent",...}]}
    - {"reports": [{"campaignId": X, "rows": [...]}]}
    """
    out: list[dict] = []
    rows = response.get("rows") or []
    reports = response.get("reports") or []

    if rows:
        for r in rows:
            row = _build_stat_row(r, account_id=account_id, campaign_id=None)
            if row:
                out.append(row)

    for report in reports:
        cid = str(report.get("campaignId") or report.get("id") or "")
        for r in report.get("rows", []):
            row = _build_stat_row(r, account_id=account_id, campaign_id=cid)
            if row:
                out.append(row)

    # Если response неожиданной формы — сохраним полный raw в одну строку на каждую
    # кампанию за date_from, чтобы хоть что-то заранее было видно в БД для разбора.
    if not out and fallback_campaigns:
        today = datetime.now(UTC).date()
        for cid in fallback_campaigns:
            out.append({
                "date": today,
                "ozon_campaign_id": cid,
                "product_id": NIL_UUID,
                "ozon_account_id": account_id,
                "impressions": 0,
                "clicks": 0,
                "orders": 0,
                "revenue": 0,
                "spend": 0,
                "ctr": None,
                "drr": None,
                "roas": None,
                "avg_bid": None,
                "raw_data": response,
            })
    return out


def _build_stat_row(
    r: dict, *, account_id: uuid.UUID, campaign_id: str | None
) -> dict | None:
    date_value = _parse_date(r.get("date"))
    cid = campaign_id or str(r.get("campaignId") or r.get("id") or "")
    if not date_value or not cid:
        return None

    impressions = _to_int(r.get("views") or r.get("impressions"))
    clicks = _to_int(r.get("clicks"))
    orders = _to_int(r.get("orders") or r.get("ordered"))
    revenue = _to_float(r.get("revenue") or r.get("ordersMoney"))
    spend = _to_float(r.get("moneySpent") or r.get("expense") or r.get("cost"))

    ctr = (clicks / impressions) if impressions else None
    drr = (spend / revenue) if revenue else None
    roas = (revenue / spend) if spend else None

    return {
        "date": date_value,
        "ozon_campaign_id": cid,
        "product_id": NIL_UUID,  # без разбивки по товарам
        "ozon_account_id": account_id,
        "impressions": impressions,
        "clicks": clicks,
        "orders": orders,
        "revenue": revenue,
        "spend": spend,
        "ctr": round(ctr, 4) if ctr is not None else None,
        "drr": round(drr, 4) if drr is not None else None,
        "roas": round(roas, 4) if roas is not None else None,
        "avg_bid": None,
        "raw_data": r,
    }


def _parse_date(value) -> date_cls | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date_cls.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def _to_float(value) -> float:
    """Ozon Performance отдаёт money-поля в ru-локали ('635,33'). Нормализуем."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(" ", "").replace(" ", "")
    # '1.234,56' (rare) → '1234.56'; '635,33' → '635.33'
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value) -> int:
    """Целые тоже могут прийти строкой — поддерживаем дробные через _to_float."""
    if value is None or value == "":
        return 0
    try:
        return int(float(_to_float(value)))
    except (TypeError, ValueError):
        return 0
