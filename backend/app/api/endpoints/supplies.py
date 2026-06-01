"""
/supplies — ручной учёт поставок (MVP).

Поставка = «машина/вагон» внутри 1+ SKU. Затраты бывают общие (на поставку) или
на конкретный SKU. final_unit_cost вписывается ВРУЧНУЮ — авто-распределения нет.
total_cost / Σ затрат — справочно, в себестоимость не пишутся.

Endpoints:
- GET    /supplies                              — список с агрегатами
- POST   /supplies                              — создать (items + costs + dates)
- GET    /supplies/{id}                         — детальный
- PATCH  /supplies/{id}                         — обновить (full replace items/costs)
- DELETE /supplies/{id}                         — удалить (cascade документы из S3)
- GET    /supplies/lookup/products              — список SKU без фильтра по кабинету (для дропдауна)
- POST   /supplies/{id}/documents               — multipart upload в S3
- GET    /supplies/{id}/documents/{doc_id}/url  — presigned URL для скачивания
- DELETE /supplies/{id}/documents/{doc_id}      — удалить документ + объект из S3
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import (
    OzonAccount,
    Product,
    Supply,
    SupplyCost,
    SupplyDocument,
    SupplyItem,
    User,
)
from app.services.s3_storage import delete_object, generate_presigned_url, upload_bytes

router = APIRouter()
UTC = timezone.utc

# Разрешённые MIME для документов поставки
ALLOWED_MIME_PREFIXES = ("application/pdf", "image/", "application/vnd.")
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 МБ


# ============================================================
# Schemas
# ============================================================


class SupplyItemIn(BaseModel):
    product_id: uuid.UUID | None = None
    offer_id: str | None = None
    qty: int = Field(..., gt=0)
    final_unit_cost: Decimal | None = None
    note: str | None = None
    # Если фронт передаст id — апдейтим (для PATCH), иначе создаём
    id: uuid.UUID | None = None


class SupplyCostIn(BaseModel):
    name: str
    amount: Decimal = Field(..., ge=0)
    scope: Literal["supply", "item"] = "supply"
    supply_item_index: int | None = Field(
        None, description="Индекс позиции в массиве items (если scope=item), нумерация с 0",
    )
    note: str | None = None
    id: uuid.UUID | None = None


class SupplyCreate(BaseModel):
    name: str
    notes: str | None = None
    cabinet_id: uuid.UUID | None = None
    total_cost: Decimal | None = None
    payment_date: date_cls | None = None
    dispatch_date: date_cls | None = None
    dispatch_from: str | None = None
    actual_departure_date: date_cls | None = None
    supply_date: date_cls | None = None
    items: list[SupplyItemIn] = []
    costs: list[SupplyCostIn] = []


class SupplyItemRow(BaseModel):
    id: str
    product_id: str | None
    offer_id: str | None
    product_name: str | None
    qty: int
    final_unit_cost: float | None
    note: str | None


class SupplyCostRow(BaseModel):
    id: str
    name: str
    amount: float
    scope: str
    supply_item_id: str | None
    note: str | None


class SupplyDocRow(BaseModel):
    id: str
    filename: str
    mime: str | None
    size: int | None
    supply_item_id: str | None
    uploaded_at: str


class SupplyDetail(BaseModel):
    id: str
    name: str
    notes: str | None
    cabinet_id: str | None
    cabinet_name: str | None
    total_cost: float | None
    payment_date: str | None
    dispatch_date: str | None
    dispatch_from: str | None
    actual_departure_date: str | None
    supply_date: str | None
    items: list[SupplyItemRow]
    costs: list[SupplyCostRow]
    documents: list[SupplyDocRow]
    # Справочно — для подсказки юзеру при ручном пересчёте себестоимости
    total_costs_sum: float
    created_at: str


class SupplyListRow(BaseModel):
    id: str
    name: str
    supply_date: str | None
    items_count: int
    costs_sum: float
    docs_count: int


class ProductLookup(BaseModel):
    id: str
    offer_id: str
    ozon_sku: int
    name: str
    cabinet_name: str


# ============================================================
# Helpers
# ============================================================


async def _get_supply_owned(db: AsyncSession, supply_id: uuid.UUID, company_id: uuid.UUID) -> Supply:
    supply = (await db.execute(
        select(Supply).where(Supply.id == supply_id, Supply.company_id == company_id)
        .options(
            selectinload(Supply.items),
            selectinload(Supply.costs),
            selectinload(Supply.documents),
        )
    )).scalar_one_or_none()
    if not supply:
        raise HTTPException(404, "Поставка не найдена")
    return supply


async def _resolve_offer_id(db: AsyncSession, product_id: uuid.UUID | None) -> str | None:
    if not product_id:
        return None
    row = (await db.execute(select(Product.offer_id).where(Product.id == product_id))).first()
    return row[0] if row else None


async def _to_detail(db: AsyncSession, supply: Supply) -> SupplyDetail:
    cabinet_name = None
    if supply.cabinet_id:
        row = (await db.execute(
            select(OzonAccount.name).where(OzonAccount.id == supply.cabinet_id)
        )).first()
        cabinet_name = row[0] if row else None

    # Карта product_id → name для items
    product_names: dict[uuid.UUID, str] = {}
    if supply.items:
        prod_ids = [i.product_id for i in supply.items if i.product_id]
        if prod_ids:
            rows = (await db.execute(
                select(Product.id, Product.name).where(Product.id.in_(prod_ids))
            )).all()
            product_names = {r.id: r.name for r in rows}

    return SupplyDetail(
        id=str(supply.id),
        name=supply.name,
        notes=supply.notes,
        cabinet_id=str(supply.cabinet_id) if supply.cabinet_id else None,
        cabinet_name=cabinet_name,
        total_cost=float(supply.total_cost) if supply.total_cost is not None else None,
        payment_date=supply.payment_date.isoformat() if supply.payment_date else None,
        dispatch_date=supply.dispatch_date.isoformat() if supply.dispatch_date else None,
        dispatch_from=supply.dispatch_from,
        actual_departure_date=(
            supply.actual_departure_date.isoformat()
            if supply.actual_departure_date else None
        ),
        supply_date=supply.supply_date.isoformat() if supply.supply_date else None,
        items=[
            SupplyItemRow(
                id=str(it.id),
                product_id=str(it.product_id) if it.product_id else None,
                offer_id=it.offer_id,
                product_name=(
                    product_names.get(it.product_id) if it.product_id else None
                ),
                qty=it.qty,
                final_unit_cost=(
                    float(it.final_unit_cost) if it.final_unit_cost is not None else None
                ),
                note=it.note,
            )
            for it in supply.items
        ],
        costs=[
            SupplyCostRow(
                id=str(c.id), name=c.name, amount=float(c.amount), scope=c.scope,
                supply_item_id=str(c.supply_item_id) if c.supply_item_id else None,
                note=c.note,
            )
            for c in supply.costs
        ],
        documents=[
            SupplyDocRow(
                id=str(d.id), filename=d.filename, mime=d.mime, size=d.size,
                supply_item_id=str(d.supply_item_id) if d.supply_item_id else None,
                uploaded_at=d.uploaded_at.isoformat(),
            )
            for d in supply.documents
        ],
        total_costs_sum=sum(float(c.amount) for c in supply.costs),
        created_at=supply.created_at.isoformat(),
    )


def _link_costs_to_items(items: list[SupplyItem], costs_in: list[SupplyCostIn]) -> dict[int, uuid.UUID]:
    """Маппим индекс позиции (с фронта) на её id (из БД) для scope='item' затрат."""
    return {idx: items[idx].id for idx in range(len(items))}


# ============================================================
# Endpoints
# ============================================================


@router.get("/lookup/products", response_model=list[ProductLookup])
async def lookup_products(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProductLookup]:
    """Дропдаун: ВСЕ SKU компании одним списком (без фильтра по кабинету)."""
    rows = (await db.execute(
        select(Product.id, Product.offer_id, Product.ozon_sku, Product.name, OzonAccount.name.label("cabinet"))
        .join(OzonAccount, OzonAccount.id == Product.ozon_account_id)
        .where(
            OzonAccount.company_id == current_user.company_id,
            Product.deleted_at.is_(None),
        )
        .order_by(Product.offer_id)
    )).all()
    return [
        ProductLookup(
            id=str(r.id), offer_id=r.offer_id or "", ozon_sku=r.ozon_sku or 0,
            name=r.name or "", cabinet_name=r.cabinet or "",
        )
        for r in rows
    ]


@router.get("", response_model=list[SupplyListRow])
async def list_supplies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SupplyListRow]:
    supplies = (await db.execute(
        select(Supply).where(Supply.company_id == current_user.company_id)
        .options(
            selectinload(Supply.items),
            selectinload(Supply.costs),
            selectinload(Supply.documents),
        )
        .order_by(Supply.supply_date.desc().nullslast(), Supply.created_at.desc())
    )).scalars().all()
    return [
        SupplyListRow(
            id=str(s.id), name=s.name,
            supply_date=s.supply_date.isoformat() if s.supply_date else None,
            items_count=len(s.items),
            costs_sum=sum(float(c.amount) for c in s.costs),
            docs_count=len(s.documents),
        )
        for s in supplies
    ]


@router.post("", response_model=SupplyDetail)
async def create_supply(
    payload: SupplyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SupplyDetail:
    if payload.cabinet_id:
        ok = (await db.execute(
            select(OzonAccount.id).where(
                OzonAccount.id == payload.cabinet_id,
                OzonAccount.company_id == current_user.company_id,
            )
        )).scalar_one_or_none()
        if not ok:
            raise HTTPException(404, "Кабинет не найден или не принадлежит компании")

    supply = Supply(
        company_id=current_user.company_id,
        user_id=current_user.id,
        cabinet_id=payload.cabinet_id,
        name=payload.name,
        notes=payload.notes,
        total_cost=payload.total_cost,
        payment_date=payload.payment_date,
        dispatch_date=payload.dispatch_date,
        dispatch_from=payload.dispatch_from,
        actual_departure_date=payload.actual_departure_date,
        supply_date=payload.supply_date,
    )
    db.add(supply)
    await db.flush()

    # Items
    items: list[SupplyItem] = []
    for it_in in payload.items:
        offer_id = it_in.offer_id or await _resolve_offer_id(db, it_in.product_id)
        item = SupplyItem(
            supply_id=supply.id,
            product_id=it_in.product_id,
            offer_id=offer_id,
            qty=it_in.qty,
            final_unit_cost=it_in.final_unit_cost,
            note=it_in.note,
        )
        db.add(item)
        items.append(item)
    await db.flush()

    # Costs (linking item-scoped via index in items array)
    idx_to_item_id = _link_costs_to_items(items, payload.costs)
    for c_in in payload.costs:
        item_id = None
        if c_in.scope == "item" and c_in.supply_item_index is not None:
            item_id = idx_to_item_id.get(c_in.supply_item_index)
        db.add(SupplyCost(
            supply_id=supply.id,
            supply_item_id=item_id,
            name=c_in.name,
            amount=c_in.amount,
            scope=c_in.scope,
            note=c_in.note,
        ))

    await db.commit()
    supply = await _get_supply_owned(db, supply.id, current_user.company_id)
    return await _to_detail(db, supply)


@router.get("/{supply_id}", response_model=SupplyDetail)
async def get_supply(
    supply_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SupplyDetail:
    supply = await _get_supply_owned(db, supply_id, current_user.company_id)
    return await _to_detail(db, supply)


@router.patch("/{supply_id}", response_model=SupplyDetail)
async def update_supply(
    supply_id: uuid.UUID,
    payload: SupplyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SupplyDetail:
    """Full-replace items/costs (документы сохраняем — у них своя жизнь)."""
    supply = await _get_supply_owned(db, supply_id, current_user.company_id)
    if payload.cabinet_id and payload.cabinet_id != supply.cabinet_id:
        ok = (await db.execute(
            select(OzonAccount.id).where(
                OzonAccount.id == payload.cabinet_id,
                OzonAccount.company_id == current_user.company_id,
            )
        )).scalar_one_or_none()
        if not ok:
            raise HTTPException(404, "Кабинет не найден")
    supply.cabinet_id = payload.cabinet_id
    supply.name = payload.name
    supply.notes = payload.notes
    supply.total_cost = payload.total_cost
    supply.payment_date = payload.payment_date
    supply.dispatch_date = payload.dispatch_date
    supply.dispatch_from = payload.dispatch_from
    supply.actual_departure_date = payload.actual_departure_date
    supply.supply_date = payload.supply_date
    supply.updated_at = datetime.now(UTC)

    # Full-replace items and costs.
    # Документы и их supply_item_id могут потерять ссылку — обнулим supply_item_id
    # для документов, чтобы FK не сломался (ondelete='SET NULL' уже стоит).
    await db.execute(delete(SupplyCost).where(SupplyCost.supply_id == supply_id))
    await db.execute(delete(SupplyItem).where(SupplyItem.supply_id == supply_id))
    await db.flush()

    items: list[SupplyItem] = []
    for it_in in payload.items:
        offer_id = it_in.offer_id or await _resolve_offer_id(db, it_in.product_id)
        item = SupplyItem(
            supply_id=supply.id,
            product_id=it_in.product_id,
            offer_id=offer_id,
            qty=it_in.qty,
            final_unit_cost=it_in.final_unit_cost,
            note=it_in.note,
        )
        db.add(item)
        items.append(item)
    await db.flush()

    idx_to_item_id = _link_costs_to_items(items, payload.costs)
    for c_in in payload.costs:
        item_id = None
        if c_in.scope == "item" and c_in.supply_item_index is not None:
            item_id = idx_to_item_id.get(c_in.supply_item_index)
        db.add(SupplyCost(
            supply_id=supply.id,
            supply_item_id=item_id,
            name=c_in.name,
            amount=c_in.amount,
            scope=c_in.scope,
            note=c_in.note,
        ))

    await db.commit()
    supply = await _get_supply_owned(db, supply.id, current_user.company_id)
    return await _to_detail(db, supply)


@router.delete("/{supply_id}", status_code=204)
async def delete_supply(
    supply_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    supply = await _get_supply_owned(db, supply_id, current_user.company_id)
    # Удаляем объекты S3 перед сносом из БД (best-effort, не валим если S3 промахнётся)
    for doc in supply.documents:
        try:
            await delete_object(doc.s3_key)
        except Exception:
            pass  # noqa: S110 — best-effort cleanup
    await db.execute(delete(Supply).where(Supply.id == supply_id))
    await db.commit()


# ============================================================
# Документы
# ============================================================


@router.post("/{supply_id}/documents", response_model=SupplyDocRow)
async def upload_document(
    supply_id: uuid.UUID,
    file: UploadFile = File(...),
    supply_item_id: uuid.UUID | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SupplyDocRow:
    supply = await _get_supply_owned(db, supply_id, current_user.company_id)

    # Валидация MIME
    mime = file.content_type or "application/octet-stream"
    if not any(mime.startswith(p) for p in ALLOWED_MIME_PREFIXES):
        raise HTTPException(415, f"Тип файла {mime} не разрешён")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, f"Файл больше {MAX_FILE_SIZE // 1024 // 1024} МБ")

    # Если supply_item_id указан — проверяем что он принадлежит этой supply
    if supply_item_id:
        if not any(it.id == supply_item_id for it in supply.items):
            raise HTTPException(404, "Позиция не принадлежит этой поставке")

    # Ключ S3
    file_uuid = uuid.uuid4().hex[:12]
    safe_filename = (file.filename or "file").replace("/", "_").replace("\\", "_")
    s3_key = f"supplies/{supply.user_id}/{supply.id}/{file_uuid}_{safe_filename}"

    await upload_bytes(content=content, key=s3_key, mime=mime)

    doc = SupplyDocument(
        supply_id=supply.id,
        supply_item_id=supply_item_id,
        filename=safe_filename,
        s3_key=s3_key,
        mime=mime,
        size=len(content),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return SupplyDocRow(
        id=str(doc.id), filename=doc.filename, mime=doc.mime, size=doc.size,
        supply_item_id=str(doc.supply_item_id) if doc.supply_item_id else None,
        uploaded_at=doc.uploaded_at.isoformat(),
    )


@router.get("/{supply_id}/documents/{doc_id}/url")
async def get_document_url(
    supply_id: uuid.UUID,
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    supply = await _get_supply_owned(db, supply_id, current_user.company_id)
    doc = next((d for d in supply.documents if d.id == doc_id), None)
    if not doc:
        raise HTTPException(404, "Документ не найден")
    url = await generate_presigned_url(doc.s3_key, expires=3600)
    return {"url": url, "filename": doc.filename, "expires_in": 3600}


@router.delete("/{supply_id}/documents/{doc_id}", status_code=204)
async def delete_document(
    supply_id: uuid.UUID,
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    supply = await _get_supply_owned(db, supply_id, current_user.company_id)
    doc = next((d for d in supply.documents if d.id == doc_id), None)
    if not doc:
        raise HTTPException(404, "Документ не найден")
    try:
        await delete_object(doc.s3_key)
    except Exception:
        pass
    await db.execute(delete(SupplyDocument).where(SupplyDocument.id == doc_id))
    await db.commit()
