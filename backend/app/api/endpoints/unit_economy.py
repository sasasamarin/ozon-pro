"""
Импорт XLSX «Экономика магазина → Общие расходы» Ozon Seller UI.

Два endpoint'а:
1. POST /finance/unit-economy/preview — парсит файл, считает сверку,
   возвращает превью БЕЗ записи в БД. Юзер видит что прилетело.
2. POST /finance/unit-economy/commit — записывает в monthly_unit_economy
   с upsert по (cabinet_id, sku, month).

Принцип: подтверждение перед коммитом. Точное «зеркало Ozon».
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.deps_cabinets import get_accessible_cabinet_ids
from app.db.session import get_db
from app.models import MonthlyUnitEconomy, OzonAccount, User
from app.services.unit_economy_parser import (
    ParseResult, parse_unit_economy, verify_row_profit,
)

router = APIRouter()
UTC = timezone.utc


class RowSummary(BaseModel):
    sku: int
    offer_id: str | None = None
    name: str | None = None
    delivered_qty: int | None = None
    returned_qty: int | None = None
    revenue: float | None = None
    spp_points: float | None = None
    ozon_commission: float | None = None
    storage: float | None = None
    ozon_profit: float | None = None
    computed_profit: float
    diff: float
    sverka_ok: bool


class PreviewResponse(BaseModel):
    cabinet_id: str
    cabinet_name: str
    period_from: str
    period_to: str
    month: str
    file_name: str
    rows_count: int
    skipped_rows: int
    unknown_columns: list[str]
    total_revenue: float
    total_spp_points: float
    total_partner_programs: float
    total_seller_revenue: float
    total_ozon_profit: float
    total_computed_profit: float
    sverka_pass_count: int
    sverka_fail_count: int
    sample_rows: list[RowSummary]


@router.post("/preview", response_model=PreviewResponse)
async def preview_upload(
    file: UploadFile = File(...),
    cabinet_id: uuid.UUID = Form(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PreviewResponse:
    """Парсит XLSX, возвращает превью без записи в БД."""
    cabinet = await _validate_cabinet(db, cabinet_id, current_user)
    parsed = await _parse_upload(file)
    # Валидация: SKU из XLSX должны быть среди products выбранного кабинета.
    # Иначе юзер выбрал не тот кабинет (артикулы soluna есть в home, не в Stolz).
    file_skus = [int(r["sku"]) for r in parsed.rows if r.get("sku")]
    if file_skus:
        from sqlalchemy import text as _txt
        matched = (await db.execute(_txt("""
            SELECT COUNT(DISTINCT ozon_sku)
            FROM products
            WHERE ozon_account_id = :acc AND ozon_sku = ANY(:skus)
        """), {"acc": str(cabinet.id), "skus": file_skus})).scalar() or 0
        if matched == 0:
            raise HTTPException(
                400,
                f"Кабинет «{cabinet.name}» не содержит ни одного товара из файла "
                f"(проверено {len(file_skus)} SKU). Возможно, выбран не тот кабинет.",
            )
        if matched < len(file_skus) * 0.3:
            # Найдено менее 30% — подозрительно, но не блокируем
            # (новые товары могли появиться в файле раньше нашего sync_products)
            pass
    return _build_preview(cabinet, parsed)


@router.get("/status", response_model=list[dict])
async def upload_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    Список загруженных XLSX по каждому кабинету компании.
    Для UI: рядом с кабинетом показывать «XLSX за май загружен 01.06.2026».
    """
    from sqlalchemy import text as _txt
    rows = (await db.execute(_txt("""
        SELECT
          oa.id::text AS cabinet_id,
          oa.name AS cabinet_name,
          ue.month::text AS month,
          ue.period_from::text AS period_from,
          ue.period_to::text AS period_to,
          MAX(ue.imported_at)::text AS imported_at,
          COUNT(DISTINCT ue.sku) AS sku_count,
          MAX(ue.source_file) AS source_file
        FROM monthly_unit_economy ue
        JOIN ozon_accounts oa ON oa.id = ue.cabinet_id
        WHERE oa.company_id = :cid AND oa.deleted_at IS NULL
        GROUP BY oa.id, oa.name, ue.month, ue.period_from, ue.period_to
        ORDER BY oa.name, ue.month DESC
    """), {"cid": str(current_user.company_id)})).all()
    return [
        {
            "cabinet_id": r.cabinet_id,
            "cabinet_name": r.cabinet_name,
            "month": r.month,
            "period_from": r.period_from,
            "period_to": r.period_to,
            "imported_at": r.imported_at,
            "sku_count": r.sku_count,
            "source_file": r.source_file,
        }
        for r in rows
    ]


@router.get("/coverage", response_model=dict)
async def upload_coverage(
    months_back: int = 12,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Матрица покрытия XLSX: кабинет × последние N месяцев. Возвращает структуру
    {cabinets: [...], months: [...], coverage: {cabinet_id: {month: {sku, imported_at}}}},
    которая позволяет UI отрисовать grid с галочками/крестиками.

    Принцип «честность»: юзер должен видеть НЕ ТОЛЬКО что загружено, но и
    чего НЕ ХВАТАЕТ — какие месяцы остались без точных чисел Ozon.
    """
    from datetime import date, timedelta
    from sqlalchemy import select, text as _txt

    # Список кабинетов
    accessible = await get_accessible_cabinet_ids(db, current_user)
    cab_q = select(OzonAccount.id, OzonAccount.name).where(
        OzonAccount.company_id == current_user.company_id,
        OzonAccount.deleted_at.is_(None),
    ).order_by(OzonAccount.name)
    if accessible is not None:
        cab_q = cab_q.where(OzonAccount.id.in_(accessible))
    cab_rows = (await db.execute(cab_q)).all()
    cabinets = [{"id": str(r.id), "name": r.name} for r in cab_rows]

    # Список последних N месяцев (включая текущий)
    today = date.today()
    months: list[str] = []
    y, m = today.year, today.month
    for _ in range(months_back):
        months.append(date(y, m, 1).isoformat())
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months.sort()  # от старого к новому

    # Загруженные пары (cabinet_id, month) → данные
    if cabinets:
        rows = (await db.execute(_txt("""
            SELECT
              cabinet_id::text AS cid,
              month::text AS m,
              COUNT(DISTINCT sku) AS sku_cnt,
              MAX(imported_at)::text AS imp_at
            FROM monthly_unit_economy
            WHERE cabinet_id = ANY(CAST(:accs AS uuid[]))
              AND month >= CAST(:m_from AS date)
            GROUP BY cabinet_id, month
        """), {
            "accs": [c["id"] for c in cabinets],
            "m_from": months[0],
        })).all()
    else:
        rows = []

    # coverage[cabinet_id][month] = {sku_count, imported_at}
    coverage: dict[str, dict[str, dict]] = {c["id"]: {} for c in cabinets}
    for r in rows:
        coverage[r.cid][r.m[:10]] = {
            "sku_count": r.sku_cnt,
            "imported_at": r.imp_at,
        }

    return {
        "cabinets": cabinets,
        "months": months,
        "coverage": coverage,
    }


@router.post("/commit", response_model=dict)
async def commit_upload(
    file: UploadFile = File(...),
    cabinet_id: uuid.UUID = Form(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Парсит + записывает в monthly_unit_economy. Upsert по (cabinet, sku, month)."""
    cabinet = await _validate_cabinet(db, cabinet_id, current_user)
    parsed = await _parse_upload(file)

    month_date = parsed.period_from.replace(day=1)
    now = datetime.now(UTC)
    written = 0

    for row in parsed.rows:
        values = {**row,
                  "cabinet_id": cabinet.id,
                  "month": month_date,
                  "period_from": parsed.period_from,
                  "period_to": parsed.period_to,
                  "imported_at": now,
                  "source_file": parsed.file_name[:200]}

        stmt = pg_insert(MonthlyUnitEconomy).values(**values)
        update_cols = {
            k: stmt.excluded[k] for k in values
            if k not in ("cabinet_id", "sku", "month")
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["cabinet_id", "sku", "month"],
            set_=update_cols,
        )
        await db.execute(stmt)
        written += 1

    await db.commit()
    return {
        "status": "ok",
        "cabinet": cabinet.name,
        "month": month_date.isoformat(),
        "rows_written": written,
        "period_from": parsed.period_from.isoformat(),
        "period_to": parsed.period_to.isoformat(),
    }


async def _validate_cabinet(
    db: AsyncSession, cabinet_id: uuid.UUID, user: User,
) -> OzonAccount:
    cabinet = (await db.execute(
        select(OzonAccount).where(
            OzonAccount.id == cabinet_id,
            OzonAccount.company_id == user.company_id,
            OzonAccount.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not cabinet:
        raise HTTPException(404, "Кабинет не найден или не принадлежит компании")
    return cabinet


async def _parse_upload(file: UploadFile) -> ParseResult:
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Ожидается XLSX файл")
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "Файл больше 20 МБ — не наш формат")
    try:
        return parse_unit_economy(io.BytesIO(content), file_name=file.filename)
    except ValueError as e:
        raise HTTPException(400, f"Не удалось распарсить: {e}")
    except Exception as e:
        raise HTTPException(500, f"Ошибка парсинга: {type(e).__name__}: {e}")


def _build_preview(cabinet: OzonAccount, parsed: ParseResult) -> PreviewResponse:
    total_rev = sum((r.get("revenue") or 0) for r in parsed.rows)
    total_spp = sum((r.get("spp_points") or 0) for r in parsed.rows)
    total_partner = sum((r.get("partner_programs") or 0) for r in parsed.rows)
    total_ozon_profit = sum((r.get("ozon_profit") or 0) for r in parsed.rows)
    total_computed = Decimal("0")

    pass_cnt = fail_cnt = 0
    samples: list[RowSummary] = []
    sorted_rows = sorted(
        parsed.rows, key=lambda r: abs(float(r.get("revenue") or 0)), reverse=True,
    )

    for r in sorted_rows:
        computed = verify_row_profit(r)
        total_computed += computed
        ozon_p = r.get("ozon_profit") or Decimal("0")
        diff = abs(computed - ozon_p)
        ok = diff < Decimal("1")
        if ok:
            pass_cnt += 1
        else:
            fail_cnt += 1
        if len(samples) < 10:
            samples.append(RowSummary(
                sku=int(r["sku"]),
                offer_id=r.get("offer_id"),
                name=r.get("name"),
                delivered_qty=r.get("delivered_qty"),
                returned_qty=r.get("returned_qty"),
                revenue=float(r.get("revenue") or 0),
                spp_points=float(r.get("spp_points") or 0),
                ozon_commission=float(r.get("ozon_commission") or 0),
                storage=float(r.get("storage_from_xlsx") or 0),
                ozon_profit=float(ozon_p),
                computed_profit=float(computed),
                diff=float(diff),
                sverka_ok=ok,
            ))

    month_date = parsed.period_from.replace(day=1)
    return PreviewResponse(
        cabinet_id=str(cabinet.id),
        cabinet_name=cabinet.name,
        period_from=parsed.period_from.isoformat(),
        period_to=parsed.period_to.isoformat(),
        month=month_date.isoformat(),
        file_name=parsed.file_name,
        rows_count=len(parsed.rows),
        skipped_rows=parsed.skipped_rows,
        unknown_columns=parsed.unknown_columns,
        total_revenue=float(total_rev),
        total_spp_points=float(total_spp),
        total_partner_programs=float(total_partner),
        total_seller_revenue=float(total_rev + total_spp + total_partner),
        total_ozon_profit=float(total_ozon_profit),
        total_computed_profit=float(total_computed),
        sverka_pass_count=pass_cnt,
        sverka_fail_count=fail_cnt,
        sample_rows=samples,
    )
