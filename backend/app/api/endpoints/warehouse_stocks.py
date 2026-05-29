"""
Остатки по складам + сводка по кластерам.

GET /api/v1/warehouse-stocks/products/{product_id}
  → Список складов товара с остатками + velocity по cluster_from + signal

GET /api/v1/warehouse-stocks/clusters
  → Сводка по кластерам/городам: топ-проблем по стокаутам, всего товаров.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Order, OrderItem, OzonAccount, Product, Stock, User
from app.services.warehouse_cluster import parse_warehouse_name

router = APIRouter()
UTC = timezone.utc


class WarehouseStockRow(BaseModel):
    warehouse_name: str | None
    warehouse_id: int | None
    city: str | None
    cluster: str | None
    free_to_sell: int
    reserved: int
    in_transit: int
    velocity_per_day: float  # из заказов с cluster_from = этот склад
    days_left: float | None  # free_to_sell / velocity или None если velocity=0
    signal: str              # stockout | reorder_now | ok


class ProductWarehouseStocks(BaseModel):
    product_id: str
    product_name: str
    offer_id: str
    total_free_to_sell: int
    rows: list[WarehouseStockRow]
    snapshot_at: str | None


class ClusterAggRow(BaseModel):
    cluster: str
    stockout_skus: int           # cколько SKU имеют 0 в этом кластере
    reorder_now_skus: int        # < 7 дней (velocity-based)
    ok_skus: int
    total_free_to_sell: int
    velocity_per_day: float       # всех заказов из этого кластера


class ClustersSummaryResponse(BaseModel):
    clusters: list[ClusterAggRow]


async def _account_ids(
    db: AsyncSession, *, company_id: uuid.UUID
) -> list[uuid.UUID]:
    q = select(OzonAccount.id).where(
        OzonAccount.company_id == company_id,
        OzonAccount.deleted_at.is_(None),
    )
    return [r[0] for r in (await db.execute(q)).all()]


async def _velocity_per_cluster(
    db: AsyncSession,
    *,
    account_ids: list[uuid.UUID],
    product_ids: list[uuid.UUID] | None,
    days: int = 30,
) -> dict[tuple[uuid.UUID, str], float]:
    """{(product_id, cluster_from): velocity_per_day} за окно."""
    if not account_ids:
        return {}
    cutoff = datetime.now(UTC) - timedelta(days=days)
    q = (
        select(
            OrderItem.product_id,
            Order.cluster_from,
            func.coalesce(func.sum(OrderItem.quantity), 0).label("qty"),
        )
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.ozon_account_id.in_(account_ids),
            Order.order_created_at >= cutoff,
            Order.status == "delivered",
            Order.cluster_from.is_not(None),
            OrderItem.product_id.is_not(None),
        )
        .group_by(OrderItem.product_id, Order.cluster_from)
    )
    if product_ids:
        q = q.where(OrderItem.product_id.in_(product_ids))
    result: dict[tuple[uuid.UUID, str], float] = {}
    for r in (await db.execute(q)).all():
        result[(r.product_id, r.cluster_from)] = float(r.qty) / days
    return result


def _signal_for(stock: int, velocity: float) -> str:
    if stock <= 0:
        return "stockout"
    if velocity <= 0:
        return "ok"
    days_left = stock / velocity
    if days_left < 7:
        return "reorder_now"
    return "ok"


@router.get("/products/{product_id}", response_model=ProductWarehouseStocks)
async def product_warehouse_stocks(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProductWarehouseStocks:
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

    # latest snapshot FBO_WH для этого product
    latest_time = (await db.execute(
        select(func.max(Stock.time)).where(
            Stock.product_id == pid, Stock.warehouse_type == "FBO_WH"
        )
    )).scalar()

    if not latest_time:
        return ProductWarehouseStocks(
            product_id=str(prod.id), product_name=prod.name, offer_id=prod.offer_id,
            total_free_to_sell=0, rows=[], snapshot_at=None,
        )

    rows = (await db.execute(
        select(Stock).where(
            Stock.product_id == pid,
            Stock.warehouse_type == "FBO_WH",
            Stock.time == latest_time,
        )
    )).scalars().all()

    # velocity per cluster_from для этого товара
    accs = await _account_ids(db, company_id=current_user.company_id)
    vel_map = await _velocity_per_cluster(
        db, account_ids=accs, product_ids=[pid], days=30
    )

    out: list[WarehouseStockRow] = []
    total_stock = 0
    for s in rows:
        city, cluster = parse_warehouse_name(s.warehouse_name)
        velocity = vel_map.get((pid, s.warehouse_name), 0.0)
        signal = _signal_for(s.free_to_sell, velocity)
        days_left = (s.free_to_sell / velocity) if velocity > 0 else None
        total_stock += s.free_to_sell
        out.append(WarehouseStockRow(
            warehouse_name=s.warehouse_name,
            warehouse_id=s.warehouse_id,
            city=city,
            cluster=cluster,
            free_to_sell=s.free_to_sell,
            reserved=s.reserved or 0,
            in_transit=s.in_transit or 0,
            velocity_per_day=round(velocity, 2),
            days_left=round(days_left, 1) if days_left is not None else None,
            signal=signal,
        ))

    # сорт: сначала stockout, потом reorder_now, потом ok
    signal_order = {"stockout": 0, "reorder_now": 1, "ok": 2}
    out.sort(key=lambda r: (signal_order.get(r.signal, 9), r.days_left or 9999))

    return ProductWarehouseStocks(
        product_id=str(prod.id),
        product_name=prod.name,
        offer_id=prod.offer_id,
        total_free_to_sell=total_stock,
        rows=out,
        snapshot_at=latest_time.isoformat(),
    )


@router.get("/clusters", response_model=ClustersSummaryResponse)
async def clusters_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ClustersSummaryResponse:
    """Сводка по кластерам: сколько SKU в стокауте/риске/норме + velocity."""
    accs = await _account_ids(db, company_id=current_user.company_id)
    if not accs:
        return ClustersSummaryResponse(clusters=[])

    # latest per-warehouse stocks для каждого продукта
    latest_subq = (
        select(
            Stock.product_id,
            func.max(Stock.time).label("latest"),
        )
        .where(Stock.warehouse_type == "FBO_WH")
        .group_by(Stock.product_id)
        .subquery()
    )
    rows = (await db.execute(
        select(Stock)
        .join(latest_subq, (latest_subq.c.product_id == Stock.product_id)
              & (latest_subq.c.latest == Stock.time))
        .where(Stock.warehouse_type == "FBO_WH")
    )).scalars().all()

    # velocity per (product, cluster_from)
    product_ids = list({s.product_id for s in rows})
    vel_map = await _velocity_per_cluster(
        db, account_ids=accs, product_ids=product_ids, days=30
    )

    # group by cluster
    cluster_data: dict[str, dict] = defaultdict(lambda: {
        "stockout_skus": 0, "reorder_now_skus": 0, "ok_skus": 0,
        "total_free_to_sell": 0, "velocity": 0.0,
    })

    for s in rows:
        _, cluster = parse_warehouse_name(s.warehouse_name)
        if not cluster:
            cluster = "(не определён)"
        velocity = vel_map.get((s.product_id, s.warehouse_name), 0.0)
        signal = _signal_for(s.free_to_sell, velocity)
        d = cluster_data[cluster]
        d["total_free_to_sell"] += s.free_to_sell
        d["velocity"] += velocity
        if signal == "stockout":
            d["stockout_skus"] += 1
        elif signal == "reorder_now":
            d["reorder_now_skus"] += 1
        else:
            d["ok_skus"] += 1

    items = [
        ClusterAggRow(
            cluster=name,
            stockout_skus=d["stockout_skus"],
            reorder_now_skus=d["reorder_now_skus"],
            ok_skus=d["ok_skus"],
            total_free_to_sell=d["total_free_to_sell"],
            velocity_per_day=round(d["velocity"], 2),
        )
        for name, d in cluster_data.items()
    ]
    # сорт: сначала больше всего проблем
    items.sort(key=lambda c: (-c.stockout_skus, -c.reorder_now_skus, -c.velocity_per_day))

    return ClustersSummaryResponse(clusters=items)
