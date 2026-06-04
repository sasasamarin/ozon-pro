"""
Парсер отчёта о реализации Ozon (XLSX).

- openpyxl читает XLSX
- Извлекает: revenue, commission, logistics, payout
- Возвращает структуру для ManualReconciliation
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

from openpyxl import load_workbook


@dataclass
class OzonRealizationReport:
    revenue: float | None = 0.0
    commission: float | None = 0.0
    logistics: float | None = 0.0
    payout: float | None = 0.0
    raw_rows: list[dict] | None = field(default_factory=list)


def _to_float(val: Any) -> float:
    """Утилита для очистки чисел из Excel (пробелы, запятые)."""
    if not val:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_realization_xlsx(file_obj: str | bytes | io.BytesIO) -> OzonRealizationReport:
    """Парсит Excel-отчет о реализации Ozon."""

    if isinstance(file_obj, bytes):
        file_obj = io.BytesIO(file_obj)

    wb = load_workbook(file_obj, read_only=True, data_only=True)
    ws = wb.active

    header_row_idx = None
    headers: list[str] = []

    for i, row in enumerate(ws.iter_rows(min_row=1, max_row=20, values_only=True)):
        row_strs = [str(c).strip().lower() if c else "" for c in row]
        if any("артикул" in c or "sku" in c for c in row_strs):
            header_row_idx = i + 1
            headers = row_strs
            break

    if not header_row_idx:
        raise ValueError("Не найден заголовок таблицы в отчете о реализации")

    def find_col(keywords: list[str]) -> int | None:
        for idx, h in enumerate(headers):
            if any(kw in h for kw in keywords):
                return idx
        return None

    col_revenue = find_col(["реализовано на сумму", "цена реализации", "итого реализовано"])
    col_commission = find_col(["вознаграждение", "комиссия"])
    col_logistics = find_col(["доставка", "логистика"])
    col_payout = find_col(["к перечислению", "итого к оплате"])

    report = OzonRealizationReport()

    for row in ws.iter_rows(min_row=header_row_idx + 1, values_only=True):
        if not row or all(c is None for c in row):
            continue

        if row[0] is None and row[1] is None:
            continue

        rev = _to_float(row[col_revenue]) if col_revenue is not None else 0.0
        comm = _to_float(row[col_commission]) if col_commission is not None else 0.0
        logist = _to_float(row[col_logistics]) if col_logistics is not None else 0.0
        payout = _to_float(row[col_payout]) if col_payout is not None else 0.0

        report.revenue += rev
        report.commission += comm
        report.logistics += logist
        report.payout += payout

        if report.raw_rows is not None:
            report.raw_rows.append({
                "revenue": rev,
                "commission": comm,
                "logistics": logist,
                "payout": payout
            })

    wb.close()

    report.revenue = round(report.revenue, 2)
    report.commission = round(report.commission, 2)
    report.logistics = round(report.logistics, 2)
    report.payout = round(report.payout, 2)

    return report