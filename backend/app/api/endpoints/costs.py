"""
Себестоимость товаров: чтение + ручной ввод + CSV bulk-upload.

GET    /api/v1/costs/products            — список всех товаров с current cost
POST   /api/v1/costs/products/{id}       — ручной апдейт одной строки
POST   /api/v1/costs/upload-csv          — bulk-upload через CSV
GET    /api/v1/costs/template.csv        — скачать пустой CSV-шаблон
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import OzonAccount, Product, User
from app.models.cost import (
    CostConfidence,
    CostSource,
    PendingCost,
    ProductCostHistory,
)

router = APIRouter()
UTC = timezone.utc


class CostRow(BaseModel):
    product_id: str
    offer_id: str
    name: str
    cabinet_id: str
    cabinet_name: str
    image_url: str | None
    purchase_price: float | None
    delivery_to_wh: float | None
    packaging: float | None
    other_costs: float | None
    full_cost: float | None
    confidence: str | None        # exact / estimated / missing
    source: str | None
    effective_from: str | None


class CostUpdateRequest(BaseModel):
    purchase_price: float = Field(ge=0)
    delivery_to_wh: float = Field(ge=0, default=0)
    packaging: float = Field(ge=0, default=0)
    other_costs: float = Field(ge=0, default=0)


def _extract_image(raw: dict | None) -> str | None:
    if not isinstance(raw, dict):
        return None
    primary = raw.get("primary_image")
    if isinstance(primary, list):
        for item in primary:
            if isinstance(item, str) and item:
                return item
    elif isinstance(primary, str) and primary:
        return primary
    return None


async def _company_user_id(db: AsyncSession, *, company_id: uuid.UUID) -> uuid.UUID | None:
    """Owner-юзер компании (для product_cost_history.user_id)."""
    r = await db.execute(
        select(User.id).where(User.company_id == company_id, User.deleted_at.is_(None))
        .order_by(User.created_at).limit(1)
    )
    return r.scalar_one_or_none()


async def _latest_cost_entries(
    db: AsyncSession, *, accs: list[uuid.UUID]
) -> dict[uuid.UUID, ProductCostHistory]:
    """{product_id: latest ProductCostHistory entry}.

    Берём активную запись (effective_to IS NULL).
    """
    if not accs:
        return {}
    rows = (
        await db.execute(
            select(ProductCostHistory)
            .join(Product, Product.id == ProductCostHistory.product_id)
            .where(
                Product.ozon_account_id.in_(accs),
                ProductCostHistory.effective_to.is_(None),
            )
        )
    ).scalars().all()
    return {r.product_id: r for r in rows}


@router.get("/products", response_model=list[CostRow])
async def list_product_costs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CostRow]:
    """Список всех товаров с их latest cost-данными."""
    rows = (
        await db.execute(
            select(Product, OzonAccount.name.label("cabinet_name"))
            .join(OzonAccount, OzonAccount.id == Product.ozon_account_id)
            .where(
                OzonAccount.company_id == current_user.company_id,
                OzonAccount.deleted_at.is_(None),
                Product.deleted_at.is_(None),
            )
            .order_by(Product.name)
        )
    ).all()

    accs = list({p.Product.ozon_account_id for p in rows})
    cost_map = await _latest_cost_entries(db, accs=accs)

    result: list[CostRow] = []
    for row in rows:
        p = row.Product
        ch = cost_map.get(p.id)
        result.append(
            CostRow(
                product_id=str(p.id),
                offer_id=p.offer_id,
                name=p.name,
                cabinet_id=str(p.ozon_account_id),
                cabinet_name=row.cabinet_name,
                image_url=_extract_image(p.raw_data),
                purchase_price=float(ch.purchase_price) if ch else (float(p.cost_price) if p.cost_price else None),
                delivery_to_wh=float(ch.delivery_to_wh) if ch else None,
                packaging=float(ch.packaging) if ch else None,
                other_costs=float(ch.other_costs) if ch else None,
                full_cost=float(ch.full_cost) if ch else (float(p.cost_price) if p.cost_price else None),
                confidence=ch.confidence if ch else None,
                source=ch.source if ch else None,
                effective_from=ch.effective_from.isoformat() if ch else None,
            )
        )
    return result


@router.post("/products/{product_id}", response_model=CostRow)
async def update_product_cost(
    product_id: str,
    payload: CostUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CostRow:
    """Ручной апдейт себестоимости одного товара.

    Алгоритм:
    - Закрываем существующую active-запись (effective_to=now).
    - Insert новой с effective_from=now, confidence=exact, source=manual.
    - Денормализуем products.cost_price = purchase_price (для быстрых чтений).
    """
    try:
        pid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(400, "Невалидный product_id")

    prod = (await db.execute(
        select(Product).join(OzonAccount, OzonAccount.id == Product.ozon_account_id)
        .where(Product.id == pid, OzonAccount.company_id == current_user.company_id,
               Product.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not prod:
        raise HTTPException(404, "Товар не найден")

    user_id = await _company_user_id(db, company_id=current_user.company_id)
    if not user_id:
        raise HTTPException(500, "У компании нет владельца")

    now = datetime.now(UTC)
    full_cost = payload.purchase_price + payload.delivery_to_wh + payload.packaging + payload.other_costs

    # Закрываем active-запись для этого product (если есть)
    existing = (await db.execute(
        select(ProductCostHistory).where(
            ProductCostHistory.product_id == pid,
            ProductCostHistory.effective_to.is_(None),
        )
    )).scalars().all()
    for e in existing:
        e.effective_to = now

    # Если есть запись на сегодня (effective_from == now с микросекундной точностью
    # вряд ли), то PK не конфликтнет. Используем now (timestamp+tz).
    new_entry = ProductCostHistory(
        effective_from=now,
        product_id=pid,
        ozon_account_id=prod.ozon_account_id,
        user_id=user_id,
        purchase_price=payload.purchase_price,
        delivery_to_wh=payload.delivery_to_wh,
        packaging=payload.packaging,
        other_costs=payload.other_costs,
        full_cost=full_cost,
        source=CostSource.MANUAL.value,
        confidence=CostConfidence.EXACT.value,
        created_by_user_id=current_user.id,
    )
    db.add(new_entry)
    prod.cost_price = full_cost
    await db.commit()
    await db.refresh(new_entry)

    cabinet_row = (await db.execute(
        select(OzonAccount.name).where(OzonAccount.id == prod.ozon_account_id)
    )).scalar_one()

    return CostRow(
        product_id=str(prod.id),
        offer_id=prod.offer_id,
        name=prod.name,
        cabinet_id=str(prod.ozon_account_id),
        cabinet_name=cabinet_row,
        image_url=_extract_image(prod.raw_data),
        purchase_price=float(new_entry.purchase_price),
        delivery_to_wh=float(new_entry.delivery_to_wh),
        packaging=float(new_entry.packaging),
        other_costs=float(new_entry.other_costs),
        full_cost=float(new_entry.full_cost),
        confidence=new_entry.confidence,
        source=new_entry.source,
        effective_from=new_entry.effective_from.isoformat(),
    )


@router.get("/template.csv")
async def download_template(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """CSV-шаблон с предзаполненными offer_id'ами компании."""
    rows = (await db.execute(
        select(Product.offer_id, Product.name)
        .join(OzonAccount, OzonAccount.id == Product.ozon_account_id)
        .where(
            OzonAccount.company_id == current_user.company_id,
            OzonAccount.deleted_at.is_(None),
            Product.deleted_at.is_(None),
        )
        .order_by(Product.name)
    )).all()

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["offer_id", "name", "purchase_price", "delivery_to_wh", "packaging", "other_costs"])
    for offer_id, name in rows:
        w.writerow([offer_id, name, "", "", "", ""])

    csv_bytes = ("﻿" + buf.getvalue()).encode("utf-8")
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="flowoi_costs_template.csv"'},
    )


class CSVImportResult(BaseModel):
    total_rows: int
    matched: int
    pending_saved: int
    failed: int
    errors: list[str]


@router.post("/upload-csv", response_model=CSVImportResult)
async def upload_costs_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CSVImportResult:
    """Bulk-upload себестоимости через CSV.

    Поддерживаем 2 формата:
    1. Полный: offer_id;name;purchase_price;delivery_to_wh;packaging;other_costs
    2. Минимальный: offer_id;purchase_price (без шапки или с шапкой)

    Алгоритм: matched (product найден) → product_cost_history + cost_price.
    Unmatched → pending_costs (auto-pickup при появлении SKU).
    """
    content = (await file.read()).decode("utf-8-sig")  # snap BOM
    # Парсер пытается ; затем , как delimiter
    delim = ";" if content.count(";") > content.count(",") else ","

    reader = csv.reader(io.StringIO(content), delimiter=delim)
    rows = [r for r in reader if r]
    if not rows:
        return CSVImportResult(total_rows=0, matched=0, pending_saved=0, failed=0, errors=["Файл пуст"])

    # Detect header
    first = [c.strip().lower() for c in rows[0]]
    has_header = "offer_id" in first or "purchase_price" in first
    if has_header:
        data_rows = rows[1:]
    else:
        data_rows = rows

    user_id = await _company_user_id(db, company_id=current_user.company_id)
    if not user_id:
        raise HTTPException(500, "У компании нет владельца")

    # Products map (offer_id_lower → Product)
    accs_q = await db.execute(
        select(OzonAccount.id).where(
            OzonAccount.company_id == current_user.company_id,
            OzonAccount.deleted_at.is_(None),
        )
    )
    accs = [r[0] for r in accs_q.all()]
    products = (await db.execute(
        select(Product).where(
            Product.ozon_account_id.in_(accs), Product.deleted_at.is_(None)
        )
    )).scalars().all()
    products_by_offer: dict[str, list[Product]] = {}
    for p in products:
        key = (p.offer_id or "").strip().lower()
        if key:
            products_by_offer.setdefault(key, []).append(p)

    now = datetime.now(UTC)
    matched = 0
    pending = 0
    failed = 0
    errors: list[str] = []

    for idx, row in enumerate(data_rows, start=2 if has_header else 1):
        if not row or all(not c.strip() for c in row):
            continue
        # минимальный формат: offer_id, purchase_price (+ опционально 3 поля)
        if len(row) < 2:
            failed += 1
            errors.append(f"строка {idx}: меньше 2 полей")
            continue
        offer_id = row[0].strip()
        try:
            purchase = float(str(row[2] if len(row) >= 6 else row[1]).replace(",", ".").replace(" ", ""))
        except ValueError:
            failed += 1
            errors.append(f"строка {idx} ({offer_id}): purchase_price не число")
            continue
        # для расширенного формата
        delivery = packaging = other = 0.0
        if len(row) >= 6:
            try:
                delivery = float(str(row[3] or "0").replace(",", ".").replace(" ", "") or "0")
                packaging = float(str(row[4] or "0").replace(",", ".").replace(" ", "") or "0")
                other = float(str(row[5] or "0").replace(",", ".").replace(" ", "") or "0")
            except ValueError:
                pass

        key = offer_id.lower()
        matched_products = products_by_offer.get(key, [])

        if not matched_products:
            # Save to pending
            offer_lower = key
            await db.execute(
                __import__("sqlalchemy").text("""
                    INSERT INTO pending_costs (id, user_id, offer_id_lower, purchase_price, imported_at)
                    VALUES (:id, :uid, :offer, :price, :now)
                    ON CONFLICT (user_id, offer_id_lower) DO UPDATE
                    SET purchase_price = EXCLUDED.purchase_price, imported_at = EXCLUDED.imported_at
                """),
                {"id": uuid.uuid4(), "uid": user_id, "offer": offer_lower,
                 "price": purchase, "now": now},
            )
            pending += 1
            continue

        # apply to each matched product
        for p in matched_products:
            # close existing active
            existing = (await db.execute(
                select(ProductCostHistory).where(
                    ProductCostHistory.product_id == p.id,
                    ProductCostHistory.effective_to.is_(None),
                )
            )).scalars().all()
            for e in existing:
                e.effective_to = now
            full = purchase + delivery + packaging + other
            db.add(ProductCostHistory(
                effective_from=now,
                product_id=p.id,
                ozon_account_id=p.ozon_account_id,
                user_id=user_id,
                purchase_price=purchase,
                delivery_to_wh=delivery,
                packaging=packaging,
                other_costs=other,
                full_cost=full,
                source=CostSource.CSV.value,
                confidence=CostConfidence.EXACT.value,
                created_by_user_id=current_user.id,
            ))
            p.cost_price = full
            matched += 1

    await db.commit()

    return CSVImportResult(
        total_rows=len(data_rows),
        matched=matched,
        pending_saved=pending,
        failed=failed,
        errors=errors[:20],
    )
