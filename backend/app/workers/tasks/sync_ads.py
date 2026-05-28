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

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import log
from app.db.session import AsyncSessionLocal
from app.models import AdCampaign, AdStatistics, OzonAccount
from app.services.ozon_client import OzonAPIError
from app.services.ozon_perf_client import (
    OzonPerformanceClient,
    OzonPerfNotConfigured,
)
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import get_active_accounts, track_sync_log


# ============================================================
# TASK 1: sync_all_ad_campaigns
# ============================================================


@celery_app.task(name="app.workers.tasks.sync_ads.sync_all_ad_campaigns")
def sync_all_ad_campaigns() -> dict:
    """Список рекламных кампаний по всем активным магазинам с подключённым PA."""
    return asyncio.run(_sync_all_ad_campaigns_async())


async def _sync_all_ad_campaigns_async() -> dict:
    async with AsyncSessionLocal() as db:
        accounts = await get_active_accounts(db)

    eligible = [a for a in accounts if a.perf_client_id_encrypted]
    log.info(
        "sync_ad_campaigns_started",
        accounts_total=len(accounts),
        accounts_with_pa=len(eligible),
    )
    results = await asyncio.gather(
        *[_sync_ad_campaigns_for_account(a.id) for a in eligible],
        return_exceptions=True,
    )
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    return {
        "total": len(eligible),
        "skipped_no_pa": len(accounts) - len(eligible),
        "success": success,
        "failed": len(results) - success,
    }


async def _sync_ad_campaigns_for_account(account_id: uuid.UUID) -> dict:
    async with AsyncSessionLocal() as db:
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
            return {"status": "failed", "error": str(e)}


async def _upsert_campaign(
    db: AsyncSession, *, account_id: uuid.UUID, raw: dict
) -> None:
    ozon_campaign_id = str(raw.get("id") or raw.get("campaignId") or "")
    if not ozon_campaign_id:
        return

    payload: dict[str, Any] = {
        "ozon_account_id": account_id,
        "ozon_campaign_id": ozon_campaign_id,
        "title": raw.get("title") or raw.get("name") or f"Кампания {ozon_campaign_id}",
        "campaign_type": str(raw.get("advObjectType") or raw.get("type") or "unknown").lower(),
        "state": str(raw.get("state") or "unknown").lower(),
        "from_date": _parse_date(raw.get("fromDate")),
        "to_date": _parse_date(raw.get("toDate")),
        "daily_budget": _to_float(raw.get("dailyBudget")),
        "weekly_budget": _to_float(raw.get("weeklyBudget")),
        "budget": _to_float(raw.get("budget")),
        "raw_data": raw,
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
def sync_all_ad_statistics(days_window: int = 3) -> dict:
    """Дневная статистика рекламы по всем активным магазинам с PA."""
    return asyncio.run(_sync_all_ad_statistics_async(days_window))


async def _sync_all_ad_statistics_async(days_window: int) -> dict:
    async with AsyncSessionLocal() as db:
        accounts = await get_active_accounts(db)

    eligible = [a for a in accounts if a.perf_client_id_encrypted]
    log.info(
        "sync_ad_statistics_started",
        accounts_with_pa=len(eligible),
        days=days_window,
    )
    results = await asyncio.gather(
        *[_sync_ad_statistics_for_account(a.id, days_window) for a in eligible],
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
    account_id: uuid.UUID, days_window: int
) -> dict:
    async with AsyncSessionLocal() as db:
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
                        index_elements=["date", "ozon_campaign_id"],
                        set_={
                            col: stmt.excluded[col]
                            for col in (
                                "views", "clicks", "orders", "revenue",
                                "money_spent", "ctr", "drr", "raw_data",
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
                "ozon_account_id": account_id,
                "views": 0,
                "clicks": 0,
                "orders": 0,
                "revenue": 0,
                "money_spent": 0,
                "ctr": None,
                "drr": None,
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

    views = _to_int(r.get("views") or r.get("impressions"))
    clicks = _to_int(r.get("clicks"))
    orders = _to_int(r.get("orders") or r.get("ordered"))
    revenue = _to_float(r.get("revenue") or r.get("ordersMoney"))
    spent = _to_float(r.get("moneySpent") or r.get("expense") or r.get("cost"))

    ctr = (clicks / views) if views else None
    drr = (spent / revenue) if revenue else None

    return {
        "date": date_value,
        "ozon_campaign_id": cid,
        "ozon_account_id": account_id,
        "views": views,
        "clicks": clicks,
        "orders": orders,
        "revenue": revenue,
        "money_spent": spent,
        "ctr": round(ctr, 4) if ctr is not None else None,
        "drr": round(drr, 4) if drr is not None else None,
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


def _to_int(value) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _to_float(value) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
