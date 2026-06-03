"""
Финансовые отчёты Ozon — async flow request/poll/download.

Probe Ozon API (2026-06-03, FlowoiAUDIT.md A3):
- POST /v1/report/finance/create — 404, Ozon закрыл создание через API.
  → СОЗДАВАТЬ отчёт может только юзер в UI Ozon.
- POST /v1/report/list — 200, отдаёт ГОТОВЫЕ отчёты с downloadable XLSX (S3).
  → ПОДХВАТЫВАЕМ через /list, парсим, складываем в БД.

Типы отчётов фактически (242 шт у home на 2026-06-03):
- seller_postings — детальный список постингов с финразбивкой (43 шт).
- seller_placement_by_products — point-of-sale хранение per SKU (6 шт,
  уже парсится в sync_placement_reports).
- seller_discounted — отчёт по уценённым товарам (1 шт).
- realization — НЕ в /v1/report/list (отдельный endpoint /v2/finance/realization).
- finance_summary / mutual_settlement — появляются если юзер явно заказал в UI.

Этот сервис:
  1) request_report() — НЕ создаёт отчёт (Ozon endpoint закрыт). Возвращает
     структурированный ответ с инструкцией.
  2) discover_reports() — ищет готовые в /v1/report/list по типу.
  3) poll_report_status() — статус по конкретному code.
  4) download_and_parse() — скачивает XLSX → openpyxl → агрегаты.
  5) sync_report_to_db() — создаёт/обновляет FinancialReport.
"""
from __future__ import annotations

import io
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import httpx
import openpyxl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import log
from app.core.security import decrypt_secret
from app.models import OzonAccount, FinancialReport, FinancialReportStatus
from app.services.ozon_client import OzonSellerClient


@dataclass
class ReportRequest:
    ozon_account_id: uuid.UUID
    report_type: str  # значение FinancialReportType
    period_from: date
    period_to: date


@dataclass
class ReportInfo:
    code: str
    file_url: str | None
    status: str  # 'success' | 'processing' | 'waiting' | 'failed'
    report_type: str
    created_at: str | None
    error: str | None


@dataclass
class ParseResult:
    rows_parsed: int
    total_accrued: float | None
    total_withheld: float | None
    total_to_payout: float | None
    sample_rows: list[dict]


# === 1. REQUEST — Ozon закрыл, говорим юзеру ===============================


async def request_report(req: ReportRequest) -> dict[str, Any]:
    """
    Endpoint POST /v1/report/finance/create удалён у Ozon (404 на 2026-06-03).
    Возвращает структурированный ответ для UI.
    """
    return {
        "ozon_report_code": None,
        "status": "manual_required",
        "message": (
            "Ozon закрыл создание финансовых отчётов через API. "
            "Зайди в кабинет Ozon → Финансы → Заказать отчёт. "
            "Когда Ozon его подготовит — мы автоматически подхватим "
            "через /v1/report/list (раз в час). Тип отчёта: "
            f"'{req.report_type}', период {req.period_from}…{req.period_to}."
        ),
    }


# === 2. DISCOVER — поиск готовых отчётов в /v1/report/list =================


async def discover_reports(
    db: AsyncSession, account_id: uuid.UUID,
    report_type: str | None = None,
    limit: int = 50,
) -> list[ReportInfo]:
    """
    Ищет ГОТОВЫЕ отчёты в Ozon /v1/report/list для конкретного кабинета.
    Фильтр report_type — если None, возвращает все типы.
    """
    acc = (await db.execute(
        select(OzonAccount).where(OzonAccount.id == account_id)
    )).scalar_one_or_none()
    if not acc:
        return []
    cid = decrypt_secret(acc.client_id_encrypted)
    apk = decrypt_secret(acc.api_key_encrypted)
    headers = {"Client-Id": cid, "Api-Key": apk, "Content-Type": "application/json"}

    out: list[ReportInfo] = []
    async with OzonSellerClient(cid, apk) as client:
        page = 1
        while page <= 10 and len(out) < limit:
            try:
                r = await client._client.post(
                    "/v1/report/list",
                    json={"page": page, "page_size": 50, "report_type": "ALL"},
                    headers=headers,
                )
                if r.status_code != 200:
                    log.warning("report_list_bad", account=str(account_id),
                                status=r.status_code, body=r.text[:200])
                    break
                j = r.json()
                reps = (j.get("result") or {}).get("reports") or []
                if not reps:
                    break
                for rep in reps:
                    rtype = rep.get("report_type") or ""
                    if report_type and rtype != report_type:
                        continue
                    out.append(ReportInfo(
                        code=rep.get("code") or "",
                        file_url=rep.get("file") or None,
                        status=rep.get("status") or "unknown",
                        report_type=rtype,
                        created_at=rep.get("created_at"),
                        error=rep.get("error") or None,
                    ))
                    if len(out) >= limit:
                        break
                page += 1
            except Exception as e:  # noqa: BLE001
                log.exception("report_list_failed", account=str(account_id), err=str(e))
                break
    return out


# === 3. POLL — статус по коду =============================================


async def poll_report_status(
    db: AsyncSession, account_id: uuid.UUID, report_code: str,
) -> ReportInfo | None:
    """Найти конкретный отчёт по code в /v1/report/list."""
    found = await discover_reports(db, account_id, limit=500)
    for r in found:
        if r.code == report_code:
            return r
    return None


# === 4. DOWNLOAD + PARSE ===================================================


async def download_xlsx(file_url: str) -> bytes | None:
    """Скачать XLSX по downloadable-URL Ozon (S3)."""
    if not file_url:
        return None
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            r = await client.get(file_url)
            if r.status_code != 200:
                log.warning("report_download_bad", url_prefix=file_url[:60],
                            status=r.status_code)
                return None
            return r.content
        except httpx.HTTPError as e:
            log.exception("report_download_network", err=str(e))
            return None


def parse_xlsx_generic(content: bytes) -> ParseResult:
    """
    Generic парсер: открывает XLSX, читает первый лист, агрегирует
    числовые колонки по эвристике («Начислено», «Удержано», «К выплате»).
    Точные парсеры для специфичных типов отчётов — отдельно
    (placement_report_parser для seller_placement_by_products).
    """
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001
        log.exception("xlsx_parse_failed", err=str(e))
        return ParseResult(0, None, None, None, [])

    sheet = wb.active
    if sheet is None:
        return ParseResult(0, None, None, None, [])

    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return ParseResult(0, None, None, None, [])

    header_idx = next((i for i, r in enumerate(rows) if r and any(r)), 0)
    headers = [str(h or "").strip() for h in rows[header_idx]]
    data_rows = rows[header_idx + 1:]

    def find_col(needles: list[str]) -> int | None:
        for i, h in enumerate(headers):
            h_low = (h or "").lower()
            for n in needles:
                if n in h_low:
                    return i
        return None

    accrued_col = find_col(["начислен"])
    withheld_col = find_col(["удержан", "вычет"])
    payout_col = find_col(["к выплате", "итого"])

    total_accrued = 0.0 if accrued_col is not None else None
    total_withheld = 0.0 if withheld_col is not None else None
    total_payout = 0.0 if payout_col is not None else None

    sample: list[dict] = []
    rows_count = 0
    for row in data_rows:
        if not row or not any(row):
            continue
        rows_count += 1
        if accrued_col is not None:
            try:
                total_accrued += float(row[accrued_col] or 0)
            except (ValueError, TypeError):
                pass
        if withheld_col is not None:
            try:
                total_withheld += float(row[withheld_col] or 0)
            except (ValueError, TypeError):
                pass
        if payout_col is not None:
            try:
                total_payout += float(row[payout_col] or 0)
            except (ValueError, TypeError):
                pass
        if len(sample) < 5:
            sample.append({h: row[i] for i, h in enumerate(headers) if i < len(row)})

    return ParseResult(
        rows_parsed=rows_count,
        total_accrued=round(total_accrued, 2) if total_accrued is not None else None,
        total_withheld=round(total_withheld, 2) if total_withheld is not None else None,
        total_to_payout=round(total_payout, 2) if total_payout is not None else None,
        sample_rows=sample,
    )


async def download_and_parse(
    db: AsyncSession, account_id: uuid.UUID, report_code: str,
) -> dict[str, Any]:
    """End-to-end: найти отчёт → скачать → парсить → вернуть dict."""
    info = await poll_report_status(db, account_id, report_code)
    if not info:
        return {"error": "Отчёт не найден в /v1/report/list"}
    if info.status != "success":
        return {
            "error": f"Отчёт не готов (status={info.status})",
            "report_status": info.status,
        }
    if not info.file_url:
        return {"error": "Нет URL для скачивания"}

    content = await download_xlsx(info.file_url)
    if not content:
        return {"error": "Не удалось скачать XLSX"}

    parsed = parse_xlsx_generic(content)
    return {
        "report_code": report_code,
        "report_type": info.report_type,
        "rows_parsed": parsed.rows_parsed,
        "total_accrued": parsed.total_accrued,
        "total_withheld": parsed.total_withheld,
        "total_to_payout": parsed.total_to_payout,
        "sample_rows": parsed.sample_rows,
    }


# === 5. SYNC TO DB — обновляем FinancialReport ============================


async def sync_report_to_db(
    db: AsyncSession, account_id: uuid.UUID, user_id: uuid.UUID,
    info: ReportInfo, parsed: ParseResult | None = None,
) -> FinancialReport:
    """Создать/обновить FinancialReport-запись из ReportInfo."""
    existing = (await db.execute(
        select(FinancialReport).where(
            FinancialReport.ozon_report_code == info.code,
            FinancialReport.ozon_account_id == account_id,
        )
    )).scalar_one_or_none()

    status_map = {
        "success": FinancialReportStatus.READY.value,
        "processing": FinancialReportStatus.PROCESSING.value,
        "waiting": FinancialReportStatus.REQUESTED.value,
        "failed": FinancialReportStatus.FAILED.value,
    }
    status = status_map.get(info.status, FinancialReportStatus.REQUESTED.value)

    if existing:
        existing.status = status
        existing.raw_file_url = info.file_url
        if parsed:
            existing.total_accrued = parsed.total_accrued
            existing.total_withheld = parsed.total_withheld
            existing.total_to_payout = parsed.total_to_payout
            existing.ready_at = datetime.utcnow()
        return existing

    today = date.today()
    rep = FinancialReport(
        ozon_account_id=account_id, user_id=user_id,
        report_type=info.report_type, period_from=today, period_to=today,
        status=status, ozon_report_code=info.code, raw_file_url=info.file_url,
        total_accrued=parsed.total_accrued if parsed else None,
        total_withheld=parsed.total_withheld if parsed else None,
        total_to_payout=parsed.total_to_payout if parsed else None,
        ready_at=datetime.utcnow() if parsed else None,
        raw_data={"source": "v1_report_list", "info": info.__dict__},
    )
    db.add(rep)
    await db.flush()
    return rep
