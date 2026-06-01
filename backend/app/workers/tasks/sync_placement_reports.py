"""
Авто-синк отчётов «Размещение по товарам» (seller_placement_by_products) из Ozon.

Точное per-SKU хранение/реклама/эквайринг публичный API напрямую не отдаёт.
Но Ozon генерирует XLSX-отчёт seller_placement_by_products (тот же что юзер
выгружает в UI «Финансы → Экономика магазина → Общие расходы»), который
доступен через /v1/report/list. Endpoint создания закрыт, но
УЖЕ СОЗДАННЫЕ отчёты можно скачивать через API — это и делаем.

Юзер один раз заказывает отчёт в Ozon UI (или это происходит автоматически
по расписанию Ozon), наш бэкенд каждый час проверяет /v1/report/list и
подхватывает новые success-отчёты, парсит и сохраняет в monthly_unit_economy.

Никакой ручной загрузки XLSX больше не нужно.
"""
from __future__ import annotations

import asyncio
import io
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.core.security import decrypt_secret
from app.models import OzonAccount, PlacementStorageDaily
from app.services.ozon_client import OzonSellerClient
from app.services.placement_report_parser import parse_placement_report
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import get_active_accounts, run_celery_async

REPORT_TYPE = "seller_placement_by_products"


@celery_app.task(
    name="app.workers.tasks.sync_placement_reports.sync_placement_reports",
    soft_time_limit=900, time_limit=1200,
    bind=True, autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 300},
)
def sync_placement_reports(self) -> dict:
    """Синкает свежие seller_placement_by_products отчёты со всех кабинетов."""
    return run_celery_async(_sync_async)


async def _sync_async(SessionLocal: async_sessionmaker[AsyncSession]) -> dict:
    async with SessionLocal() as db:
        accounts = await get_active_accounts(db)

    # Параллельно по кабинетам
    results = await asyncio.gather(*[
        _sync_one_cabinet(SessionLocal, acc) for acc in accounts
    ], return_exceptions=True)

    summary = {"cabinets": len(accounts), "imported_files": 0, "upserted_rows": 0,
               "errors": 0, "by_cabinet": {}}
    for acc, res in zip(accounts, results):
        if isinstance(res, Exception):
            log.exception("placement_cabinet_failed", account=str(acc.id))
            summary["errors"] += 1
            summary["by_cabinet"][str(acc.id)] = {"error": str(res)[:200]}
        else:
            summary["imported_files"] += res.get("imported_files", 0)
            summary["upserted_rows"] += res.get("upserted_rows", 0)
            summary["by_cabinet"][str(acc.id)] = res
    return summary


async def _sync_one_cabinet(
    SessionLocal: async_sessionmaker[AsyncSession], acc: OzonAccount,
) -> dict:
    cid = decrypt_secret(acc.client_id_encrypted)
    apk = decrypt_secret(acc.api_key_encrypted)

    # Какие отчёты этого типа УЖЕ загружены — храним code в source_report daily-таблицы
    async with SessionLocal() as db:
        seen_codes = set((await db.execute(text("""
            SELECT DISTINCT source_report FROM placement_storage_daily
            WHERE cabinet_id = :cab AND source_report LIKE :pattern
        """), {"cab": str(acc.id), "pattern": f"REPORT_{REPORT_TYPE}_%"})).scalars().all())

    new_imported = 0
    upserted = 0

    async with OzonSellerClient(cid, apk) as client:
        # Тянем все отчёты этого типа — обычно их немного (1-5 на кабинет в месяц)
        page = 1
        candidates: list[dict] = []
        while page <= 5:
            lst = await client._request("POST", "/v1/report/list",
                json={"page": page, "page_size": 50, "report_type": "ALL"})
            reports = (lst.get("result") or {}).get("reports") or []
            if not reports:
                break
            for r in reports:
                if (r.get("report_type") == REPORT_TYPE
                        and r.get("status") == "success"
                        and r.get("code")
                        and r["code"] not in seen_codes):
                    candidates.append(r)
            if len(reports) < 50:
                break
            page += 1

        log.info("placement_reports_found",
                 account=str(acc.id), new_candidates=len(candidates),
                 already_synced=len(seen_codes))

        # Скачиваем и парсим
        for rep in candidates:
            code = rep["code"]
            try:
                # Получаем свежий signed URL (он действителен 3 часа)
                info = await client._request("POST", "/v1/report/info", json={"code": code})
                file_url = (info.get("result") or {}).get("file")
                if not file_url:
                    log.warning("placement_no_file_url", account=str(acc.id), code=code)
                    continue

                async with httpx.AsyncClient(timeout=120) as h:
                    resp = await h.get(file_url)
                    resp.raise_for_status()
                content = resp.content
                log.info("placement_downloaded", account=str(acc.id),
                         code=code, size=len(content))

                # Парсим в СЫРЫЕ daily-строки (sku, warehouse, day, cost).
                # PK по дню → идемпотентно: перекрывающиеся отчёты не двойнят.
                parsed = parse_placement_report(io.BytesIO(content))
                log.info("placement_parsed",
                         account=str(acc.id), code=code,
                         rows_total=parsed.rows_total,
                         rows_with_cost=parsed.rows_with_cost,
                         daily_rows=len(parsed.daily_rows))

                now = datetime.now(UTC)
                async with SessionLocal() as db:
                    # UPSERT в placement_storage_daily — никакого CASE.
                    # PK (cabinet, sku, warehouse, day) → дубль = тот же ключ → UPDATE.
                    for row in parsed.daily_rows:
                        # Знак как в Ozon: расход → отрицательно. API даёт + → −abs.
                        values = {
                            "cabinet_id": acc.id,
                            "sku": row.sku,
                            "warehouse": row.warehouse or "",
                            "day": row.day,
                            "storage_cost": -abs(row.storage_cost),
                            "source_report": code[:200],
                            "imported_at": now,
                        }
                        stmt = pg_insert(PlacementStorageDaily).values(**values)
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["cabinet_id", "sku", "warehouse", "day"],
                            set_={
                                "storage_cost": stmt.excluded.storage_cost,
                                "source_report": stmt.excluded.source_report,
                                "imported_at": stmt.excluded.imported_at,
                            },
                        )
                        await db.execute(stmt)
                        upserted += 1
                    await db.commit()
                new_imported += 1
                log.info("placement_imported", account=str(acc.id), code=code,
                         period=f"{parsed.period_from}..{parsed.period_to}",
                         daily_rows=len(parsed.daily_rows))

            except Exception as e:
                log.exception("placement_import_failed",
                              account=str(acc.id), code=code, err=str(e))
                continue

    return {
        "imported_files": new_imported,
        "upserted_rows": upserted,
        "candidates_total": len(candidates),
        "already_synced": len(seen_codes),
    }
