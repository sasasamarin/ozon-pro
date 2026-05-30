"""
Единая функция остатков — используется во ВСЕХ эндпоинтах.

Цель: в каждом разделе UI остаток одного и того же товара отображается одинаково.
До этого было: где-то SUM по всем строкам stocks (включая дубли AGG+FBO+FBO_WH),
где-то — только FBO, где-то — только AGG.

Эта функция всегда:
- Берёт ПОСЛЕДНИЙ снимок (max time) на товар
- Считает available = free_to_sell − reserved (то что реально можно продать)
- Возвращает разбивку по складам и кластерам (на основе warehouse_name → cluster)
- НЕ дублирует данные между AGG и FBO_WH (использует только FBO_WH если есть,
  иначе FBO/FBS как fallback)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Stock
from app.services.warehouse_cluster import parse_warehouse_name


@dataclass
class WarehouseStockRow:
    warehouse_type: str
    warehouse_name: str | None
    city: str | None
    cluster: str | None
    free_to_sell: int
    reserved: int
    in_transit: int

    @property
    def available(self) -> int:
        return max(0, self.free_to_sell - self.reserved)


@dataclass
class StockSummary:
    total_free_to_sell: int
    total_reserved: int
    total_in_transit: int
    total_available: int  # free − reserved
    by_warehouse: list[WarehouseStockRow]
    by_cluster: list[tuple[str, int]]  # (cluster, total_available)
    by_type: dict[str, int]  # {"FBO": 103, "FBS": 0, "RFBS": 0}
    snapshot_at: datetime | None
    has_per_warehouse: bool  # True если есть FBO_WH разбивка, иначе только агрегаты

    def to_dict(self) -> dict:
        return {
            "total_free_to_sell": self.total_free_to_sell,
            "total_reserved": self.total_reserved,
            "total_in_transit": self.total_in_transit,
            "total_available": self.total_available,
            "by_warehouse": [
                {
                    "warehouse_type": w.warehouse_type,
                    "warehouse_name": w.warehouse_name,
                    "city": w.city,
                    "cluster": w.cluster,
                    "free_to_sell": w.free_to_sell,
                    "reserved": w.reserved,
                    "in_transit": w.in_transit,
                    "available": w.available,
                }
                for w in self.by_warehouse
            ],
            "by_cluster": [{"cluster": c, "available": v} for c, v in self.by_cluster],
            "by_type": self.by_type,
            "snapshot_at": self.snapshot_at.isoformat() if self.snapshot_at else None,
            "has_per_warehouse": self.has_per_warehouse,
        }


async def get_stock(db: AsyncSession, product_id: uuid.UUID) -> StockSummary:
    """Единая точка остатков для одного товара. Используй ВО ВСЕХ разделах."""
    # 1. Последнее `time` отдельно для FBO_WH (per-warehouse) и для агрегатов
    last_wh = (await db.execute(
        select(func.max(Stock.time)).where(
            Stock.product_id == product_id,
            Stock.warehouse_type == "FBO_WH",
        )
    )).scalar_one_or_none()
    last_agg = (await db.execute(
        select(func.max(Stock.time)).where(
            Stock.product_id == product_id,
            Stock.warehouse_type.in_(("AGG", "FBO", "FBS", "RFBS")),
        )
    )).scalar_one_or_none()

    has_per_wh = last_wh is not None
    snapshot_at = max(filter(None, [last_wh, last_agg]), default=None)

    by_wh: list[WarehouseStockRow] = []
    by_type: dict[str, int] = {}

    # 2. Если есть FBO_WH разбивка — берём её per-warehouse
    if has_per_wh:
        rows = (await db.execute(
            select(Stock).where(
                Stock.product_id == product_id,
                Stock.warehouse_type == "FBO_WH",
                Stock.time == last_wh,
            )
        )).scalars().all()
        for s in rows:
            city, cluster = parse_warehouse_name(s.warehouse_name)
            by_wh.append(WarehouseStockRow(
                warehouse_type="FBO_WH",
                warehouse_name=s.warehouse_name,
                city=city, cluster=cluster,
                free_to_sell=int(s.free_to_sell or 0),
                reserved=int(s.reserved or 0),
                in_transit=int(s.in_transit or 0),
            ))

    # 3. Для FBS/RFBS (которые НЕ покрываются stock_on_warehouses) — берём агрегат
    if last_agg:
        fb_types = ("FBS", "RFBS") if has_per_wh else ("FBO", "FBS", "RFBS", "AGG")
        rows = (await db.execute(
            select(Stock).where(
                Stock.product_id == product_id,
                Stock.warehouse_type.in_(fb_types),
                Stock.time == last_agg,
            )
        )).scalars().all()
        # на каждый warehouse_type — одна агрегатная строка
        seen_types: set[str] = set()
        for s in rows:
            wt = s.warehouse_type
            if wt in seen_types:
                continue
            seen_types.add(wt)
            free = int(s.free_to_sell or 0)
            res = int(s.reserved or 0)
            tr = int(s.in_transit or 0)
            if free + res + tr == 0:
                continue
            by_wh.append(WarehouseStockRow(
                warehouse_type=wt,
                warehouse_name=None,
                city=None, cluster=None,
                free_to_sell=free, reserved=res, in_transit=tr,
            ))

    # 4. Считаем агрегаты
    total_free = sum(w.free_to_sell for w in by_wh)
    total_res = sum(w.reserved for w in by_wh)
    total_tr = sum(w.in_transit for w in by_wh)
    total_av = sum(w.available for w in by_wh)
    for w in by_wh:
        by_type[w.warehouse_type] = by_type.get(w.warehouse_type, 0) + w.available

    # by_cluster — только из FBO_WH строк (где warehouse_name заполнен)
    by_cluster_dict: dict[str, int] = {}
    for w in by_wh:
        if w.cluster:
            by_cluster_dict[w.cluster] = by_cluster_dict.get(w.cluster, 0) + w.available
    by_cluster = sorted(by_cluster_dict.items(), key=lambda x: -x[1])

    # Сортировка by_warehouse: сначала per-warehouse по available, потом FBS/RFBS
    by_wh.sort(key=lambda w: (
        0 if w.warehouse_type == "FBO_WH" else 1,
        -w.available,
    ))

    return StockSummary(
        total_free_to_sell=total_free,
        total_reserved=total_res,
        total_in_transit=total_tr,
        total_available=total_av,
        by_warehouse=by_wh,
        by_cluster=by_cluster,
        by_type=by_type,
        snapshot_at=snapshot_at,
        has_per_warehouse=has_per_wh,
    )


async def get_stocks_batch(
    db: AsyncSession, product_ids: list[uuid.UUID]
) -> dict[uuid.UUID, StockSummary]:
    """Версия для списков — для /products, /analytics/stockouts и т.д.

    Делает по запросу на каждый товар (медленно для 1000+ товаров,
    зато логика идентична `get_stock`). Если нужна высокая производительность —
    переписать через one-shot CTE.
    """
    out: dict[uuid.UUID, StockSummary] = {}
    for pid in product_ids:
        out[pid] = await get_stock(db, pid)
    return out
