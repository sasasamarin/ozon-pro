"""
/api/v1/storage-warning — алерты «не попасть на хранение».

Бриф (раздел 5):
- Надёжное ядро: days_of_inventory = остаток / скорость.
- Факт: placement_storage_daily (расход за день).
- Два режима:
  · A. живой подсорт: скорость > 0 → рекомендация уменьшить дозаказ
  · B. мёртвый сток: скорость упала → распродажа/вывоз
- Два уровня сигнала:
  · 🟡 «следить» — days_of_inventory > 60, расход на хранение > 5% маржи
  · 🔴 «действовать» — мёртвый сток ИЛИ storage_ratio > 0.3
- Каждое число помечено source-флагом (api/estimated).

Литровая оценка тарифа Ozon — отложена (нужна миграция stocks.volume +
конфиг тарифов из dev.ozon.ru). Это «хрупкое = оценка» из брифа.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.deps_cabinets import get_accessible_cabinet_ids, verify_cabinet_access
from app.db.session import get_db
from app.models import OzonAccount, User


router = APIRouter()


# Пороги
DAYS_INVENTORY_YELLOW = 60
DAYS_INVENTORY_RED = 120
DEAD_STOCK_VELOCITY = 0.1   # < 0.1 продажи в день = «мёртвый» (3 в месяц)
STORAGE_SHARE_YELLOW = 0.05  # хранение > 5% от выручки → следить
STORAGE_SHARE_RED = 0.20     # > 20% → действовать


Verdict = Literal["red", "yellow", "green", "no_data"]


class WarningItem(BaseModel):
    product_id: str
    name: str | None
    offer_id: str | None
    ozon_sku: int | None
    cabinet_name: str
    # факты
    current_stock: int
    daily_velocity: float | None   # шт/день за 30д (по delivered)
    days_of_inventory: float | None
    storage_30d_rub: float          # фактический расход на хранение за 30д
    revenue_30d_rub: float
    storage_share_pct: float | None  # storage / revenue × 100
    # вердикт
    verdict: Verdict
    reason: str
    recommendation: str
    mode: Literal["A_live", "B_dead", "unknown"]  # A_live = подсорт, B_dead = мёртвый


class WarningResponse(BaseModel):
    items: list[WarningItem]
    summary: dict


@router.get("/", response_model=WarningResponse)
async def storage_warning(
    cabinet_id: uuid.UUID | None = Query(None),
    only_problematic: bool = Query(True, description="Только 🔴/🟡 — без green/no_data"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WarningResponse:
    """
    Список SKU с warning по хранению. Каждой строке — вердикт + рекомендация.
    """
    cab_filter = ""
    params: dict = {"cid": str(current_user.company_id)}
    if cabinet_id:
        # проверка что кабинет наш
        ok = (await db.execute(select(OzonAccount.id).where(
            OzonAccount.id == cabinet_id,
            OzonAccount.company_id == current_user.company_id,
        ))).scalar_one_or_none()
        if not ok:
            raise HTTPException(404, "Кабинет не ваш")
        await verify_cabinet_access(db, current_user, cabinet_id)
        cab_filter = "AND oa.id = :cab"
        params["cab"] = str(cabinet_id)
    else:
        # RBAC: если у юзера ограниченный MAA — режем SQL по доступным cabinet_id
        accessible = await get_accessible_cabinet_ids(db, current_user)
        if accessible is not None:
            cab_filter = "AND oa.id = ANY(:cabs)"
            params["cabs"] = [str(c) for c in accessible]

    # ОДИН большой SQL — всё одной агрегацией.
    # Stock-блок копирует паттерн из products.py: FBO_WH (per-warehouse)
    # ИЛИ AGG/FBO/FBS/RFBS, но не оба — иначе дубли (видели stock=23427).
    # storage_30d матчится через order_items.ozon_sku (variant SKU), не
    # products.ozon_sku (primary) — placement_storage_daily.sku хранится
    # как variant.
    rows = (await db.execute(text(f"""
        WITH last_wh AS (
            SELECT product_id, MAX(time) t FROM stocks
            WHERE warehouse_type='FBO_WH' AND time > NOW() - INTERVAL '7 days'
            GROUP BY product_id
        ),
        last_agg AS (
            SELECT product_id, MAX(time) t FROM stocks
            WHERE warehouse_type IN ('AGG','FBO','FBS','RFBS')
              AND time > NOW() - INTERVAL '7 days'
            GROUP BY product_id
        ),
        wh_sum AS (
            SELECT s.product_id,
                   COALESCE(SUM(GREATEST(s.free_to_sell - s.reserved, 0)), 0)::int AS total
            FROM stocks s JOIN last_wh l ON l.product_id=s.product_id AND l.t=s.time
            WHERE s.warehouse_type='FBO_WH'
            GROUP BY s.product_id
        ),
        agg_sum AS (
            SELECT s.product_id,
                   COALESCE(SUM(GREATEST(s.free_to_sell - s.reserved, 0)), 0)::int AS total
            FROM stocks s JOIN last_agg l ON l.product_id=s.product_id AND l.t=s.time
            WHERE s.warehouse_type IN ('FBS','RFBS')
               OR (s.warehouse_type IN ('AGG','FBO')
                   AND NOT EXISTS (SELECT 1 FROM last_wh w WHERE w.product_id=s.product_id))
            GROUP BY s.product_id
        ),
        velocity_30d AS (
            SELECT oi.product_id,
                   SUM(oi.quantity) FILTER (WHERE o.status='delivered')::float / 30 AS daily,
                   COALESCE(SUM(oi.price * oi.quantity) FILTER (WHERE o.status='delivered'), 0)::float AS revenue_30d
            FROM order_items oi JOIN orders o ON o.id = oi.order_id
            WHERE o.order_created_at >= NOW() - INTERVAL '30 days'
            GROUP BY oi.product_id
        ),
        product_variant_skus AS (
            -- mapping product_id ↔ все variant SKU встречавшиеся в заказах
            SELECT DISTINCT oi.product_id, oi.ozon_sku
            FROM order_items oi
            WHERE oi.product_id IS NOT NULL AND oi.ozon_sku > 0
        ),
        storage_30d AS (
            SELECT pvs.product_id,
                   SUM(ABS(ps.storage_cost))::float AS storage_30d
            FROM placement_storage_daily ps
            JOIN product_variant_skus pvs ON pvs.ozon_sku = ps.sku
            JOIN products p2 ON p2.id = pvs.product_id
            WHERE ps.day >= CURRENT_DATE - INTERVAL '30 days'
              AND ps.cabinet_id = p2.ozon_account_id
            GROUP BY pvs.product_id
        )
        SELECT
            p.id::text                AS product_id,
            p.name, p.offer_id, p.ozon_sku,
            oa.id::text               AS cabinet_id,
            oa.name                   AS cabinet_name,
            (COALESCE(wh.total, 0) + COALESCE(ag.total, 0))::int AS stock,
            COALESCE(v.daily, 0)::float AS daily_velocity,
            COALESCE(v.revenue_30d, 0)::float AS revenue_30d,
            COALESCE(s.storage_30d, 0)::float AS storage_30d
        FROM products p
        JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
        LEFT JOIN wh_sum wh ON wh.product_id = p.id
        LEFT JOIN agg_sum ag ON ag.product_id = p.id
        LEFT JOIN velocity_30d v ON v.product_id = p.id
        LEFT JOIN storage_30d s ON s.product_id = p.id
        WHERE oa.company_id = :cid
          AND oa.deleted_at IS NULL
          AND p.is_archived = false
          {cab_filter}
        ORDER BY p.name
    """), params)).all()

    items: list[WarningItem] = []
    counts = {"red": 0, "yellow": 0, "green": 0, "no_data": 0}
    total_storage_30d = 0.0

    for r in rows:
        stock = int(r.stock or 0)
        vel = float(r.daily_velocity or 0)
        revenue = float(r.revenue_30d or 0)
        storage = float(r.storage_30d or 0)
        total_storage_30d += storage

        # Расчёт
        doi: float | None = (stock / vel) if vel > 0 else None
        storage_share: float | None = (storage / revenue) if revenue > 0 else None

        # Вердикт
        verdict: Verdict = "no_data"
        reason = ""
        rec = ""
        mode: Literal["A_live", "B_dead", "unknown"] = "unknown"

        if stock == 0 and storage == 0:
            verdict = "no_data"
            reason = "Нет остатка и нет расхода на хранение."
            rec = "Если товар активен — заведи поставку. Иначе архивируй."
        elif vel < DEAD_STOCK_VELOCITY and stock > 0:
            mode = "B_dead"
            verdict = "red"
            reason = (
                f"Мёртвый сток: {vel:.2f} продаж/день за 30 дней при остатке {stock} шт. "
                f"Хранение за 30 дней — {storage:,.0f} ₽."
            )
            rec = (
                "Распродажа со скидкой ИЛИ вывоз со склада. "
                "Каждый день — минус ₽ к марже."
            )
        elif doi is not None and doi > DAYS_INVENTORY_RED:
            mode = "A_live"
            verdict = "red"
            reason = (
                f"Запас на {doi:.0f} дней — критически много. "
                f"Хранение 30д = {storage:,.0f} ₽ ({storage_share*100:.1f}% выручки)"
                if storage_share else ""
            )
            rec = "Срочно: уменьши дозаказ или распродай часть со скидкой."
        elif (storage_share is not None and storage_share > STORAGE_SHARE_RED):
            mode = "A_live"
            verdict = "red"
            reason = (
                f"Хранение съедает {storage_share*100:.1f}% выручки "
                f"({storage:,.0f} ₽ из {revenue:,.0f} ₽ за 30 дней)."
            )
            rec = "Распродажа или вывоз. Маржа уже в минусе из-за хранения."
        elif doi is not None and doi > DAYS_INVENTORY_YELLOW:
            mode = "A_live"
            verdict = "yellow"
            reason = f"Запас на {doi:.0f} дней — стоит уменьшить дозаказ."
            rec = (
                f"Скорость {vel:.1f} шт/день — следующая поставка ~через {doi*0.7:.0f} дней. "
                "Не закупай партии «впрок»."
            )
        elif (storage_share is not None and storage_share > STORAGE_SHARE_YELLOW):
            mode = "A_live"
            verdict = "yellow"
            reason = (
                f"Хранение = {storage_share*100:.1f}% выручки "
                f"({storage:,.0f} ₽). Граница 5% — следи."
            )
            rec = "Проверь оборачиваемость, ускорь продажи или уменьши остаток."
        else:
            mode = "A_live"
            verdict = "green"
            reason = (
                f"Запас {doi:.0f} дней"
                if doi is not None else "Запас в норме"
            ) + (
                f", хранение {storage_share*100:.1f}% выручки"
                if storage_share is not None else ""
            )
            rec = "Всё ОК — можно держать дальше."

        counts[verdict] += 1
        items.append(WarningItem(
            product_id=r.product_id, name=r.name,
            offer_id=r.offer_id, ozon_sku=r.ozon_sku,
            cabinet_name=r.cabinet_name,
            current_stock=stock,
            daily_velocity=round(vel, 3) if vel > 0 else None,
            days_of_inventory=round(doi, 1) if doi is not None else None,
            storage_30d_rub=round(storage, 2),
            revenue_30d_rub=round(revenue, 2),
            storage_share_pct=round(storage_share * 100, 2) if storage_share is not None else None,
            verdict=verdict, reason=reason, recommendation=rec, mode=mode,
        ))

    if only_problematic:
        items = [i for i in items if i.verdict in ("red", "yellow")]

    # Сортировка: red → yellow → green → no_data, внутри — по storage_30d убыв.
    order = {"red": 0, "yellow": 1, "green": 2, "no_data": 3}
    items.sort(key=lambda i: (order[i.verdict], -i.storage_30d_rub))

    return WarningResponse(
        items=items,
        summary={
            "counts": counts,
            "total_storage_30d_rub": round(total_storage_30d, 2),
            "thresholds": {
                "days_inventory_yellow": DAYS_INVENTORY_YELLOW,
                "days_inventory_red": DAYS_INVENTORY_RED,
                "dead_stock_velocity_per_day": DEAD_STOCK_VELOCITY,
                "storage_share_yellow_pct": STORAGE_SHARE_YELLOW * 100,
                "storage_share_red_pct": STORAGE_SHARE_RED * 100,
            },
            "note": (
                "Литровая ₽-оценка тарифа Ozon не реализована — нет stocks.volume. "
                "Текущая оценка строится на фактическом расходе из placement_storage_daily."
            ),
        },
    )
