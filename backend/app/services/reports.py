"""
Асинхронные финансовые отчёты Ozon.

Flow:
1. POST /v1/report/finance/create → возвращает report_code
2. POST /v1/report/info {code} → проверка статуса (waiting / processing / success / failed)
3. Когда success: скачать файл по downloadable URL, распарсить, сложить в БД,
   обновить FinancialReport.status=ready

В Phase 1 — структура + заглушки. Реальная реализация в Phase 2.5
(Celery: create_report_task → polling_task через countdown).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class ReportRequest:
    ozon_account_id: str
    report_type: str  # FinancialReportType value
    period_from: date
    period_to: date


async def request_report(req: ReportRequest) -> str | None:
    """Создать запрос отчёта в Ozon, вернуть code.

    TODO: POST /v1/report/finance/create через OzonSellerClient.
    """
    return None


async def poll_report_status(report_code: str) -> str:
    """Проверить статус отчёта.

    TODO: POST /v1/report/info с code, вернуть status (requested / processing / ready / failed).
    """
    return "requested"


async def download_and_parse(report_code: str) -> dict:
    """Скачать готовый отчёт + распарсить.

    TODO: GET downloadable URL, openpyxl-парсинг, агрегаты.
    """
    return {}
