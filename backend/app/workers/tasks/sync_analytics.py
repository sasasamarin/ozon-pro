"""
Синхронизация ежедневной аналитики Ozon (метрики воронки по SKU).

Endpoint: POST /v1/analytics/data
Dimension: ["sku", "day"], метрики — стандартный набор воронки.

АРХИТЕКТУРА:
- sync_all_analytics — orchestrator. Для каждого активного кабинета бьёт
  диапазон на 30-дневные чанки и диспатчит sub-task sync_analytics_chunk.
  Каждый chunk запускается через .delay().get() — это позволяет несколько
  чанков идти параллельно через Celery workers и не валиться на soft-time-limit
  одного main-task'а.
- sync_analytics_chunk(account_id, df_iso, dt_iso) — атомарный chunk.
  Делает paginate-loop с asyncio.sleep между запросами (rate-limit на
  /v1/analytics/data у Ozon очень жёсткий) + retry-on-429.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date as date_cls, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.core.security import decrypt_secret
from app.models import AnalyticsDaily, OzonAccount, OzonAccountStatus, SyncState
from app.services.ozon_client import OzonAPIError, OzonRateLimitError, OzonSellerClient
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import (
    get_active_accounts,
    load_extended_sku_map,
    run_celery_async,
    track_sync_log,
)

_ANALYTICS_ENDPOINT = "/v1/analytics/data"  # ключ в sync_state


_METRICS = [
    # Ozon AnalyticsGetDataRequest.Metrics: max 14 items.
    "ordered_units",
    "revenue",
    "hits_view_search",
    "hits_view_pdp",
    "hits_tocart_search",
    "hits_tocart_pdp",
    "session_view_search",
    "session_view_pdp",
    "conv_tocart_search",
    "conv_tocart_pdp",
    "delivered_units",
    "returns",
    "cancellations",
    "position_category",
]

_CHUNK_DAYS = 30
_PAGE_SLEEP_S = 2.0          # Дросселируем /v1/analytics/data (rate ≤ 1 RPS у Ozon)
_RATE_LIMIT_BASE_S = 5.0     # База для exp backoff при 429 без Retry-After
_RATE_LIMIT_MAX_S = 120.0    # Потолок одного sleep при 429
_MAX_RETRIES_ON_429 = 6
# Rolling-окно: последние N дней пересинхриваем даже если cursor >= today.
# /v1/analytics/data Ozon может пересчитать агрегаты последних 7 дней
# (досчёт сессий, конверсий по поздним продажам).
_REPROCESS_TAIL_DAYS = 7


# ============================================================
# ORCHESTRATOR
# ============================================================


@celery_app.task(
    name="app.workers.tasks.sync_analytics.sync_all_analytics",
    soft_time_limit=3600,   # Orchestrator может ждать долго — sub-task'и идут параллельно
    time_limit=3900,
)
def sync_all_analytics(
    days_window: int = 3,
    date_from: str | None = None,
    account_id: str | None = None,
) -> dict:
    return run_celery_async(_orchestrate, days_window, date_from, account_id)


async def _orchestrate(
    SessionLocal: async_sessionmaker[AsyncSession],
    days_window: int,
    date_from_iso: str | None,
    account_id: str | None,
) -> dict:
    """Главный oркестратор: разбивает каждый кабинет на 30-дневные чанки и
    диспатчит их как Celery sub-task'и."""
    async with SessionLocal() as db:
        if account_id:
            acc = (
                await db.execute(
                    select(OzonAccount).where(
                        OzonAccount.id == uuid.UUID(account_id),
                        OzonAccount.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            accounts = [acc] if acc else []
        else:
            accounts = await get_active_accounts(db)

    today = datetime.now(UTC).date()
    if date_from_iso:
        try:
            date_from = date_cls.fromisoformat(date_from_iso[:10])
        except ValueError:
            return {"status": "failed", "error": f"invalid date_from={date_from_iso}"}
    else:
        date_from = today - timedelta(days=days_window)

    log.info(
        "analytics_orchestrator_start",
        accounts=len(accounts),
        df=date_from.isoformat(), dt=today.isoformat(),
    )

    # Кабинеты параллельно. Внутри кабинета чанки последовательно
    # (rate-limit /v1/analytics/data действует на Client-Id, у каждого кабинета свой).
    cabinet_results = await asyncio.gather(*[
        _sync_cabinet_chunks(SessionLocal, acc, date_from, today)
        for acc in accounts
    ], return_exceptions=True)

    summary = {
        "total_chunks": 0, "success": 0, "failed": 0, "skipped": 0,
        "records": 0, "by_account": {},
    }
    for acc, res in zip(accounts, cabinet_results):
        if isinstance(res, Exception):
            log.exception("analytics_cabinet_crash", account=str(acc.id))
            summary["by_account"][str(acc.id)] = {"error": str(res), "chunks": 0}
            summary["failed"] += 1
            continue
        summary["total_chunks"] += res["chunks"]
        summary["success"]      += res["success"]
        summary["failed"]       += res["failed"]
        summary["skipped"]      += res["skipped"]
        summary["records"]      += res["records"]
        summary["by_account"][str(acc.id)] = res
        log.info(
            "analytics_account_done",
            account=str(acc.id), account_name=acc.name, **res,
        )

    return summary


async def _get_resume_cursor(
    SessionLocal: async_sessionmaker[AsyncSession],
    cabinet_id: uuid.UUID,
) -> date_cls | None:
    """Читает sync_state.last_cursor → возвращает date_cls или None."""
    async with SessionLocal() as db:
        row = (await db.execute(
            select(SyncState.last_cursor).where(
                SyncState.cabinet_id == cabinet_id,
                SyncState.endpoint == _ANALYTICS_ENDPOINT,
            )
        )).first()
    if row and row.last_cursor:
        try:
            return date_cls.fromisoformat(row.last_cursor[:10])
        except ValueError:
            return None
    return None


async def _save_cursor(
    SessionLocal: async_sessionmaker[AsyncSession],
    cabinet_id: uuid.UUID,
    cursor: date_cls,
    *,
    synced_from: date_cls | None = None,
    status: str = "ok",
    error: str | None = None,
) -> None:
    """Upsert sync_state.last_cursor + опционально last_synced_from."""
    async with SessionLocal() as db:
        values = dict(
            cabinet_id=cabinet_id,
            endpoint=_ANALYTICS_ENDPOINT,
            last_cursor=cursor.isoformat(),
            last_synced_at=datetime.now(UTC),
            status=status,
            error_message=error[:500] if error else None,
        )
        if synced_from is not None:
            values["last_synced_from"] = synced_from.isoformat()
        stmt = pg_insert(SyncState).values(**values)
        update_set = {
            "last_cursor": stmt.excluded.last_cursor,
            "last_synced_at": stmt.excluded.last_synced_at,
            "status": stmt.excluded.status,
            "error_message": stmt.excluded.error_message,
        }
        if synced_from is not None:
            update_set["last_synced_from"] = stmt.excluded.last_synced_from
        stmt = stmt.on_conflict_do_update(
            index_elements=["cabinet_id", "endpoint"],
            set_=update_set,
        )
        await db.execute(stmt)
        await db.commit()


async def _sync_cabinet_chunks(
    SessionLocal: async_sessionmaker[AsyncSession],
    acc: OzonAccount, date_from: date_cls, today: date_cls,
) -> dict:
    """
    Внутри одного кабинета — последовательно по чанкам (1 RPM per Client-Id).
    Кабинеты вызываются параллельно из _orchestrate.

    Возобновляемость через sync_state: при втором прогоне начнём с
    cursor+1day, а не с requested date_from.
    """
    # Rolling-окно: даже если cursor=today, пересинкаем последние _REPROCESS_TAIL_DAYS.
    # Ozon может пересчитать метрики постфактум (досчёт сессий, late-conversions).
    cursor = await _get_resume_cursor(SessionLocal, acc.id)
    rolling_lower = today - timedelta(days=_REPROCESS_TAIL_DAYS)
    if cursor:
        # эффективный from = min(cursor+1, rolling_lower) если cursor >= rolling_lower,
        # иначе cursor+1 (мы ещё не догнали rolling-окно).
        if cursor >= rolling_lower:
            effective_from = rolling_lower
        else:
            effective_from = cursor + timedelta(days=1)
        if effective_from > today:
            log.info("analytics_account_up_to_date",
                     account=str(acc.id), cursor=cursor.isoformat())
            return {"chunks": 0, "success": 0, "failed": 0, "skipped": 0, "records": 0}
        # Не идём раньше изначального date_from
        if effective_from < date_from:
            effective_from = date_from
    else:
        effective_from = date_from

    chunks = _build_chunks(effective_from, today, _CHUNK_DAYS)
    log.info("analytics_cabinet_start", account=str(acc.id),
             chunks=len(chunks), df=effective_from.isoformat(), dt=today.isoformat())

    stats = {"chunks": 0, "success": 0, "failed": 0, "skipped": 0, "records": 0}
    for chunk_from, chunk_to in chunks:
        try:
            res = await _chunk_async(
                SessionLocal, str(acc.id),
                chunk_from.isoformat(), chunk_to.isoformat(),
            )
        except Exception as e:
            log.exception("analytics_chunk_crash",
                          account=str(acc.id), df=chunk_from.isoformat())
            res = {"status": "failed", "error": str(e)[:200]}

        stats["chunks"] += 1
        status = res.get("status", "failed")
        if status == "success":
            stats["success"] += 1
            stats["records"] += int(res.get("rows", 0))
            # Двигаем курсор + сохраняем нижнюю границу окна для UI freshness
            await _save_cursor(SessionLocal, acc.id, chunk_to,
                               synced_from=effective_from, status="ok")
        elif status == "skipped":
            stats["skipped"] += 1
        else:
            stats["failed"] += 1
            await _save_cursor(SessionLocal, acc.id, chunk_from,
                               synced_from=effective_from,
                               status="error", error=res.get("error"))
            # При фейле останавливаемся — следующий прогон возобновится с курсора
            break
    return stats


def _build_chunks(
    df: date_cls, dt: date_cls, days: int
) -> list[tuple[date_cls, date_cls]]:
    out: list[tuple[date_cls, date_cls]] = []
    cur = df
    while cur < dt:
        end = min(cur + timedelta(days=days), dt)
        out.append((cur, end))
        cur = end
    return out


# ============================================================
# SUB-TASK: один кабинет × один 30-дневный чанк
# ============================================================


@celery_app.task(
    name="app.workers.tasks.sync_analytics.sync_analytics_chunk",
    soft_time_limit=540,
    time_limit=600,
)
def sync_analytics_chunk(account_id: str, df_iso: str, dt_iso: str) -> dict:
    return run_celery_async(_chunk_async, account_id, df_iso, dt_iso)


async def _chunk_async(
    SessionLocal: async_sessionmaker[AsyncSession],
    account_id: str,
    df_iso: str,
    dt_iso: str,
) -> dict:
    acc_uuid = uuid.UUID(account_id)
    df = date_cls.fromisoformat(df_iso[:10])
    dt = date_cls.fromisoformat(dt_iso[:10])

    async with SessionLocal() as db:
        account = (
            await db.execute(select(OzonAccount).where(OzonAccount.id == acc_uuid))
        ).scalar_one_or_none()
        if not account:
            return {"status": "failed", "error": "account_not_found"}

        try:
            async with track_sync_log(db, account.id, "sync_analytics") as stats:
                # extended map включает SKU вариантов складов (Ozon в analytics
                # возвращает sku варианта, не primary).
                sku_to_id = await load_extended_sku_map(db, account.id)
                if not sku_to_id:
                    return {"status": "skipped", "reason": "no_products"}

                client_id = decrypt_secret(account.client_id_encrypted)
                api_key = decrypt_secret(account.api_key_encrypted)

                async with OzonSellerClient(client_id, api_key) as client:
                    rows = await _fetch_analytics_chunk(
                        client=client,
                        account_id=acc_uuid,
                        df=df,
                        dt=dt,
                        sku_to_id=sku_to_id,
                    )
                    stats.processed = len(rows)

                if rows:
                    stmt = pg_insert(AnalyticsDaily).values(rows)
                    update_cols = (
                        "ordered_units", "revenue",
                        "hits_view_search", "hits_view_pdp",
                        "hits_tocart_search", "hits_tocart_pdp",
                        "session_view_search", "session_view_pdp",
                        "conv_tocart_search", "conv_tocart_pdp",
                        "delivered_units", "returns", "cancellations",
                        "position_category",
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["date", "product_id"],
                        set_={c: stmt.excluded[c] for c in update_cols},
                    )
                    await db.execute(stmt)
                    stats.updated = len(rows)

                account.last_sync_at = datetime.now(UTC)
                account.last_sync_error = None
                account.status = OzonAccountStatus.ACTIVE.value

            await db.commit()
            return {"status": "success", "rows": len(rows)}
        except OzonAPIError as e:
            account.last_sync_error = str(e)[:500]
            await db.commit()
            log.warning(
                "analytics_chunk_failed",
                account=str(acc_uuid), df=df_iso, dt=dt_iso, error=str(e),
            )
            return {"status": "failed", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            log.exception("analytics_chunk_unexpected", account=str(acc_uuid))
            return {"status": "failed", "error": str(e)}


async def _fetch_analytics_chunk(
    *,
    client: OzonSellerClient,
    account_id: uuid.UUID,
    df: date_cls,
    dt: date_cls,
    sku_to_id: dict[int, uuid.UUID],
) -> list[dict]:
    """Paginate-loop с дросселированием и retry-on-429.

    Гарантирует ≤ 1 RPS (sleep 2с между страницами), ловит OzonRateLimitError
    и спит 30с до retry. Возвращает готовый список dict-rows для upsert.
    """
    rows: list[dict] = []
    offset = 0
    page = 0
    retries = 0
    while True:
        page += 1
        try:
            response = await client.get_analytics(
                date_from=df.isoformat(),
                date_to=dt.isoformat(),
                dimension=["sku", "day"],
                metrics=_METRICS,
                limit=1000,
                offset=offset,
            )
            retries = 0  # reset на успешный запрос
        except OzonRateLimitError as e:
            retries += 1
            if retries > _MAX_RETRIES_ON_429:
                raise OzonAPIError(f"analytics rate-limit exceeded after {_MAX_RETRIES_ON_429} retries: {e}") from e
            # Ozon часто не присылает Retry-After → exp backoff с jitter
            # вместо плоских 30s × 5 = 2.5 мин слепого ожидания.
            if e.retry_after and e.retry_after > 0:
                wait = float(e.retry_after)
            else:
                import random
                wait = min(_RATE_LIMIT_BASE_S * (2 ** (retries - 1)), _RATE_LIMIT_MAX_S)
                wait += random.uniform(0, wait * 0.2)  # jitter
            log.warning(
                "analytics_429_retry",
                account=str(account_id),
                page=page, retry=retries, wait_s=round(wait, 1),
            )
            await asyncio.sleep(wait)
            continue

        result = response.get("result") or {}
        data = result.get("data") or []

        log.info(
            "analytics_page",
            account=str(account_id),
            df=df.isoformat(), dt=dt.isoformat(),
            page=page, items=len(data),
        )

        if not data:
            break

        for entry in data:
            # Ozon-quirk: в `dimensions[].name` НЕ имя dimension'а ("sku" /
            # "day"), а человеческое имя товара ("Кофемолка ..."). Поэтому
            # порядок берём как запрашивали в request: dim[0] = sku, dim[1] = day.
            dims = entry.get("dimensions") or []
            if len(dims) < 2:
                continue
            try:
                ozon_sku = int(dims[0].get("id", 0))
            except (TypeError, ValueError):
                continue
            product_id = sku_to_id.get(ozon_sku)
            if not product_id:
                continue
            day_value = _parse_date(dims[1].get("id"))
            if not day_value:
                continue
            metric_map = dict(zip(_METRICS, entry.get("metrics", []), strict=False))
            rows.append({
                "date": day_value,
                "product_id": product_id,
                **_metric_row(metric_map),
            })

        if len(data) < 1000:
            break
        offset += 1000
        await asyncio.sleep(_PAGE_SLEEP_S)  # rate-limit budget

    # Дедуп: у extended_sku_map несколько вариантов SKU могут указывать на
    # один product → две entries для одного (date, product_id). Это валит
    # ON CONFLICT DO UPDATE (CardinalityViolationError). Суммируем метрики.
    return _aggregate_duplicates(rows)


def _aggregate_duplicates(rows: list[dict]) -> list[dict]:
    """Группируем по (date, product_id), суммируем количественные метрики,
    усредняем конверсионные (Ozon в редких случаях даёт разные SKU-варианты
    одного товара на одну дату — типично это одинаковые продажи)."""
    by_key: dict[tuple, dict] = {}
    sumable = (
        "ordered_units", "revenue",
        "hits_view_search", "hits_view_pdp",
        "hits_tocart_search", "hits_tocart_pdp",
        "session_view_search", "session_view_pdp",
        "delivered_units", "returns", "cancellations",
    )
    avgable = ("conv_tocart_search", "conv_tocart_pdp")
    for r in rows:
        key = (r["date"], r["product_id"])
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = dict(r)
            by_key[key]["_count"] = 1
            continue
        for col in sumable:
            existing[col] = (existing.get(col) or 0) + (r.get(col) or 0)
        for col in avgable:
            ev = existing.get(col) or 0
            rv = r.get(col) or 0
            existing[col] = (ev * existing["_count"] + rv) / (existing["_count"] + 1)
        # position_category — берём минимум (лучшая позиция)
        if r.get("position_category") is not None:
            pc_existing = existing.get("position_category")
            if pc_existing is None or r["position_category"] < pc_existing:
                existing["position_category"] = r["position_category"]
        existing["_count"] += 1

    out: list[dict] = []
    for v in by_key.values():
        v.pop("_count", None)
        out.append(v)
    return out


# ============================================================
# Helpers (без изменений)
# ============================================================


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


def _metric_row(m: dict) -> dict:
    return {
        "ordered_units": _to_int(m.get("ordered_units")),
        "revenue": _to_float(m.get("revenue")),
        "hits_view_search": _to_int(m.get("hits_view_search")),
        "hits_view_pdp": _to_int(m.get("hits_view_pdp")),
        "hits_tocart_search": _to_int(m.get("hits_tocart_search")),
        "hits_tocart_pdp": _to_int(m.get("hits_tocart_pdp")),
        "session_view_search": _to_int(m.get("session_view_search")),
        "session_view_pdp": _to_int(m.get("session_view_pdp")),
        "conv_tocart_search": _to_float(m.get("conv_tocart_search")),
        "conv_tocart_pdp": _to_float(m.get("conv_tocart_pdp")),
        "delivered_units": _to_int(m.get("delivered_units")),
        "returns": _to_int(m.get("returns")),
        "cancellations": _to_int(m.get("cancellations")),
        "position_category": _to_int(m.get("position_category"), nullable=True),
    }


def _to_int(value, nullable: bool = False) -> int | None:
    if value is None or value == "":
        return None if nullable else 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None if nullable else 0


def _to_float(value) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
