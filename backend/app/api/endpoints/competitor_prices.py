"""
/api/v1/competitor-prices — рыночные цены конкурентов через
Ozon Premium endpoint /v5/product/info/prices.

Что отдаёт Ozon (по живому пробу 2026-06-04):
  price_indexes:
    external_index_data:
      min_price          — мин. цена у конкурентов НА ВНЕШНИХ маркетплейсах
      price_index_value  — наш price / external_min (< 1 = мы дешевле)
    ozon_index_data:
      min_price          — мин. цена у конкурентов В ОЗОНЕ
      price_index_value
    self_marketplaces_index_data:
      min_price          — наши же товары на других площадках
    color_index          — SUPER / BLUE / YELLOW / RED — метка Ozon

В отличие от MPSTATS / парсинга — это ОФИЦИАЛЬНЫЕ данные от Ozon про
рынок. Бесплатно на Premium Plus.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.deps_cabinets import get_accessible_cabinet_ids
from app.core.logging import log
from app.core.security import decrypt_secret
from app.db.session import get_db
from app.models import OzonAccount, User
from app.services.ozon_client import OzonSellerClient


router = APIRouter()


ColorIndex = Literal["SUPER", "BLUE", "YELLOW", "RED", "NO_INDEX", "WITHOUT_INDEX", ""]


class CompetitorPriceRow(BaseModel):
    product_id: str
    offer_id: str | None
    ozon_sku: int | None
    cabinet_name: str

    # Наша цена
    our_price_rub: float | None
    marketing_seller_price_rub: float | None
    old_price_rub: float | None
    min_allowed_price_rub: float | None  # минимально допустимая для продавца

    # Конкуренты
    external_min_price_rub: float | None     # мин цена на внешних маркетплейсах
    external_index: float | None             # наша / external (< 1 = мы дешевле)
    ozon_min_price_rub: float | None         # мин цена у других продавцов в Ozon
    ozon_index: float | None
    self_other_marketplaces_min_rub: float | None  # наша же цена на других площадках
    color_index: str | None                  # SUPER / BLUE / YELLOW / RED

    verdict: str                              # человечески — что Ozon говорит
    recommendation: str | None                # action item для пользователя


def _color_verdict(color: str | None) -> tuple[str, str | None]:
    """Преобразовать color_index Ozon в человеческое описание + action."""
    if not color:
        return "Без индекса", None
    c = color.upper()
    if c == "SUPER":
        return ("Супер-цена — мы лидер по цене",
                "Маржа возможно занижена. Если стабильно — рассмотреть подъём цены.")
    if c == "BLUE":
        return ("Хорошая цена — конкурентоспособная",
                None)
    if c == "YELLOW":
        return ("Жёлтый — близко к границе",
                "Конкуренты подбираются. Следить за остатками + ДРР.")
    if c == "RED":
        return ("Красный — мы дороже рынка",
                "ВНИМАНИЕ: рассмотреть снижение цены или акцент на ценность. "
                "Конкуренты получают трафик.")
    return (f"Индекс: {c}", None)


@router.get("/")
async def competitor_prices_list(
    cabinet_id: uuid.UUID | None = Query(None),
    only_red_yellow: bool = Query(False, description="Только проблемные (RED/YELLOW)"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Список SKU с ценами конкурентов из /v5/product/info/prices.
    Свежие данные напрямую от Ozon — кэш не нужен (быстрый endpoint).
    """
    # Найти все active кабинеты company
    accessible = await get_accessible_cabinet_ids(db, current_user)
    q = select(OzonAccount).where(
        OzonAccount.company_id == current_user.company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if accessible is not None:
        q = q.where(OzonAccount.id.in_(accessible))
    if cabinet_id:
        q = q.where(OzonAccount.id == cabinet_id)
    accs = (await db.execute(q)).scalars().all()
    if not accs:
        raise HTTPException(404, "Нет активных кабинетов")

    # Параллельно для каждого кабинета дёргаем /v5/product/info/prices
    async def _fetch_one(acc: OzonAccount) -> list[CompetitorPriceRow]:
        cid = decrypt_secret(acc.client_id_encrypted)
        apk = decrypt_secret(acc.api_key_encrypted)
        rows: list[CompetitorPriceRow] = []
        async with OzonSellerClient(cid, apk) as client:
            cursor = ""
            page = 0
            while page < 5:  # safety: max 5 страниц × 100 = 500 SKU
                page += 1
                payload = {
                    "filter": {"product_id": [], "visibility": "ALL"},
                    "limit": 100,
                    "cursor": cursor,
                }
                try:
                    r = await client._request("POST", "/v5/product/info/prices", json=payload)
                except Exception as e:  # noqa: BLE001
                    log.warning("competitor_prices_fetch_failed", account=str(acc.id), err=str(e))
                    break
                items = r.get("items") or []
                if not items:
                    break
                for it in items:
                    price = it.get("price") or {}
                    idx = it.get("price_indexes") or {}
                    ext = idx.get("external_index_data") or {}
                    ozon_idx = idx.get("ozon_index_data") or {}
                    self_other = idx.get("self_marketplaces_index_data") or {}
                    color = idx.get("color_index") or ""
                    verdict, rec = _color_verdict(color)

                    ext_min = float(ext.get("min_price") or 0) or None
                    ozon_min = float(ozon_idx.get("min_price") or 0) or None
                    self_min = float(self_other.get("min_price") or 0) or None

                    rows.append(CompetitorPriceRow(
                        product_id="",  # резолвим ниже через ozon_sku
                        offer_id=it.get("offer_id"),
                        ozon_sku=it.get("product_id"),
                        cabinet_name=acc.name,
                        our_price_rub=float(price.get("price") or 0) or None,
                        marketing_seller_price_rub=float(price.get("marketing_seller_price") or 0) or None,
                        old_price_rub=float(price.get("old_price") or 0) or None,
                        min_allowed_price_rub=float(price.get("min_price") or 0) or None,
                        external_min_price_rub=ext_min,
                        external_index=float(ext.get("price_index_value") or 0) or None,
                        ozon_min_price_rub=ozon_min,
                        ozon_index=float(ozon_idx.get("price_index_value") or 0) or None,
                        self_other_marketplaces_min_rub=self_min,
                        color_index=color or None,
                        verdict=verdict,
                        recommendation=rec,
                    ))
                cursor = r.get("cursor", "")
                if not cursor or len(items) < 100:
                    break
        return rows

    all_rows = await asyncio.gather(
        *[_fetch_one(a) for a in accs], return_exceptions=True,
    )
    flat: list[CompetitorPriceRow] = []
    for res in all_rows:
        if isinstance(res, list):
            flat.extend(res)

    # Резолвим product_id из БД по ozon_sku — для drill-down в UI
    if flat:
        from sqlalchemy import text as _t
        skus = [r.ozon_sku for r in flat if r.ozon_sku]
        if skus:
            map_rows = (await db.execute(_t("""
                SELECT id::text id, ozon_sku FROM products
                WHERE ozon_sku = ANY(:skus) AND ozon_account_id = ANY(:accs)
            """), {"skus": skus, "accs": [str(a.id) for a in accs]})).all()
            sku2id = {m.ozon_sku: m.id for m in map_rows}
            for r in flat:
                r.product_id = sku2id.get(r.ozon_sku, "")

    # Фильтр проблемных
    if only_red_yellow:
        flat = [r for r in flat if r.color_index in ("RED", "YELLOW")]

    # Сортируем: RED первыми, потом YELLOW, потом по дельте external_index
    order = {"RED": 0, "YELLOW": 1, "BLUE": 2, "SUPER": 3, "": 4, None: 4}
    flat.sort(key=lambda r: (order.get(r.color_index, 4),
                              -(r.external_min_price_rub or 0)))

    flat = flat[:limit]

    counts = {"RED": 0, "YELLOW": 0, "BLUE": 0, "SUPER": 0, "OTHER": 0}
    for r in flat:
        if r.color_index in ("RED", "YELLOW", "BLUE", "SUPER"):
            counts[r.color_index] += 1
        else:
            counts["OTHER"] += 1

    return {
        "items": [r.model_dump() for r in flat],
        "summary": {
            "total": len(flat),
            "counts_by_color": counts,
            "note": (
                "Данные напрямую из Ozon /v5/product/info/prices. "
                "external_min_price — минимальная цена у конкурентов на ДРУГИХ "
                "маркетплейсах (Wildberries и т.п.), ozon_min_price — конкуренты "
                "на самом Ozon. color_index — официальная метка Ozon. RED = мы дороже рынка."
            ),
        },
    }
