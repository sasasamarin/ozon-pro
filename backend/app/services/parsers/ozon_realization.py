"""
Парсер отчёта о реализации Ozon (XLSX).

ЗАГЛУШКА в Phase 1. Реальная реализация:
- openpyxl читает XLSX
- Извлекает: revenue, commission, logistics, payout
- Возвращает структуру для ManualReconciliation
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OzonRealizationReport:
    revenue: float | None = None
    commission: float | None = None
    logistics: float | None = None
    payout: float | None = None
    raw_rows: list[dict] | None = None


def parse_realization_xlsx(file_path: str) -> OzonRealizationReport:
    """ЗАГЛУШКА. Реализация в Phase 2.5."""
    # TODO: openpyxl.load_workbook(file_path), читать таблицу, агрегировать
    return OzonRealizationReport()
