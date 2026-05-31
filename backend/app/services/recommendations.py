"""
Сервис-агрегатор: собирает данные из БД + зовёт forecasting-модули
+ собирает ProductRecommendation для API/UI.

Принцип:
- Каждый продукт получает ВСЕ доступные метрики (buyout, velocity, ABC,
  procurement, ROI) с пометкой confidence.
- Если каких-то данных нет (нет себестоимости, нет supplier params) —
  соответствующая секция возвращает None, в `missing_data` пишется почему.
- UI должен показывать `missing_data` чтобы пользователь знал что включить.

Расчёт для одного продукта дешёвый (~3-5 SQL агрегатов), но при listе из
N продуктов делаем SUM по всему окну сразу (где можно) чтобы не было N+1.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, date as date_cls, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalyticsDaily, Order, OrderItem, Product, Stock
from app.models.marketplace import Cancellation, Return
from app.models.procurement import ProductSupplyParams
from app.services.warehouse_cluster import parse_warehouse_name
from app.services.forecasting import ForecastConfidence, ForecastDefaults
from app.services.forecasting.abc import abc_classify_3axis
from app.services.forecasting.buyout import BuyoutResult, calc_buyout_rate
from app.services.forecasting.procurement import recommend_procurement
from app.services.forecasting.unit_economics import calc_roi
from app.services.forecasting.velocity import VelocityResult, calc_velocity

# Дефолты для товаров без заполненных ProductSupplyParams
_DEFAULT_LEAD_TIME = 14
_DEFAULT_SAFETY_STOCK = 7
_DEFAULT_MOQ = 1
_DEFAULT_BATCH_STEP = 1
_DEFAULT_BATCH_STRICT = False


def _classify_reorder_signal(days_left: float, lead_time: int, safety: int) -> str:
    """Возвращает 'stockout' / 'reorder_now' / 'ok'.

    Логика nepsell-канон:
      days_left <= lead_time            → 🔴 stockout (опаздываешь)
      lead_time < days_left <= lead_time + safety → 🟡 reorder_now (пора заказывать)
      days_left > lead_time + safety    → 🟢 ok (запас)
    """
    if days_left <= lead_time:
        return "stockout"
    if days_left <= lead_time + safety:
        return "reorder_now"
    return "ok"

# ============================================================
#  ВНУТРЕННИЕ ХЕЛПЕРЫ — собирают сырые цифры из БД
# ============================================================


async def _gather_buyout_inputs(
    db: AsyncSession,
    *,
    ozon_account_id: uuid.UUID,
    product_id: uuid.UUID,
    ozon_sku: int,
    window_days: int,
) -> tuple[int, int, int, int]:
    """Возвращает (delivered, cancelled_in_transit, returned, arrived_total).

    Окно — последние `window_days` дней от now().
    """
    cutoff = datetime.now(UTC) - timedelta(days=window_days)

    # delivered + cancelled-in-transit за окно (из orders×order_items, чтобы
    # фильтровать по конкретному product_id)
    counts = await db.execute(
        select(
            func.coalesce(
                func.sum(case((Order.status == "delivered", OrderItem.quantity), else_=0)),
                0,
            ).label("delivered"),
            func.coalesce(
                func.sum(case((Order.status == "cancelled", OrderItem.quantity), else_=0)),
                0,
            ).label("cancelled"),
        )
        .select_from(Order)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(
            Order.ozon_account_id == ozon_account_id,
            OrderItem.product_id == product_id,
            Order.order_created_at >= cutoff,
        )
    )
    row = counts.one()
    delivered = int(row.delivered or 0)
    cancelled = int(row.cancelled or 0)

    # returns: пока матчим по product_id (если linked) ИЛИ по ozon_sku
    returns_row = await db.execute(
        select(func.coalesce(func.sum(Return.quantity), 0)).where(
            Return.ozon_account_id == ozon_account_id,
            Return.return_date >= cutoff,
            (Return.product_id == product_id) | (Return.ozon_sku == ozon_sku),
        )
    )
    returned = int(returns_row.scalar() or 0)

    arrived_total = delivered + cancelled  # cancelled-in-transit считаем как «дошедшие до решения»
    return delivered, cancelled, returned, arrived_total


async def _gather_velocity_inputs(
    db: AsyncSession,
    *,
    ozon_account_id: uuid.UUID,
    product_id: uuid.UUID,
    window_days: int,
) -> tuple[int, int, int]:
    """Возвращает (total_units_sold, days_in_stock, days_out_of_stock) за окно.

    ПРИОРИТЕТ: analytics_daily.ordered_units — самый точный источник суточной
    скорости продаж (Ozon выдаёт уже агрегированно). Если данных нет (товар
    новый или backfill не покрыл) — fallback на order_items × stocks.

    days_in_stock в новом случае: дни где ordered_units > 0 ИЛИ free_to_sell > 0
    в stocks snapshot.
    """
    cutoff_date = (datetime.now(UTC) - timedelta(days=window_days)).date()

    # === Источник 1: analytics_daily (предпочтительный) ===
    ad_row = (
        await db.execute(
            select(
                func.coalesce(func.sum(AnalyticsDaily.ordered_units), 0).label("units"),
                func.count().label("days_with_data"),
                func.count().filter(AnalyticsDaily.ordered_units > 0).label("days_with_sales"),
            ).where(
                AnalyticsDaily.product_id == product_id,
                AnalyticsDaily.date >= cutoff_date,
            )
        )
    ).one()
    ad_units = int(ad_row.units or 0)
    ad_days_with_data = int(ad_row.days_with_data or 0)

    if ad_days_with_data >= max(7, window_days // 4):
        # analytics_daily покрывает значительную часть окна — это достоверный
        # источник. Считаем days_in_stock как «дни когда товар был доступен»:
        # combine analytics-days с stocks-snapshot'ами (на случай overlap).
        stocks_days = await db.execute(
            select(
                func.count(func.distinct(func.date_trunc("day", Stock.time)))
            ).where(
                Stock.product_id == product_id,
                Stock.time >= datetime.combine(cutoff_date, datetime.min.time(), tzinfo=UTC),
                Stock.free_to_sell > 0,
            )
        )
        stocks_dis = int(stocks_days.scalar() or 0)
        # Берём максимум — analytics покрывает реальные продажи, stocks показывает наличие
        days_in_stock = max(ad_days_with_data, stocks_dis)
        days_out_of_stock = max(0, window_days - days_in_stock)
        return ad_units, days_in_stock, days_out_of_stock

    # === Источник 2 (fallback): order_items + stocks history ===
    cutoff_dt = datetime.now(UTC) - timedelta(days=window_days)
    units_row = await db.execute(
        select(func.coalesce(func.sum(OrderItem.quantity), 0))
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.ozon_account_id == ozon_account_id,
            OrderItem.product_id == product_id,
            Order.order_created_at >= cutoff_dt,
        )
    )
    units_sold = int(units_row.scalar() or 0)

    dis_row = await db.execute(
        select(
            func.count(func.distinct(func.date_trunc("day", Stock.time)))
        ).where(
            Stock.product_id == product_id,
            Stock.time >= cutoff_dt,
            Stock.free_to_sell > 0,
        )
    )
    days_in_stock = int(dis_row.scalar() or 0)
    days_out_of_stock = max(0, window_days - days_in_stock)
    return units_sold, days_in_stock, days_out_of_stock


async def _current_stock_total(db: AsyncSession, product_id: uuid.UUID) -> int:
    """SUM(free_to_sell) в последнем snapshot'е."""
    latest_time = await db.scalar(select(func.max(Stock.time)).where(Stock.product_id == product_id))
    if not latest_time:
        return 0
    total = await db.scalar(
        select(func.coalesce(func.sum(Stock.free_to_sell), 0)).where(
            Stock.product_id == product_id,
            Stock.time == latest_time,
        )
    )
    return int(total or 0)


async def _in_transit_to_customer(
    db: AsyncSession, *, ozon_account_id: uuid.UUID, product_id: uuid.UUID
) -> int:
    """Заказы в пути к покупателю (status = delivering)."""
    row = await db.execute(
        select(func.coalesce(func.sum(OrderItem.quantity), 0))
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.ozon_account_id == ozon_account_id,
            OrderItem.product_id == product_id,
            Order.status == "delivering",
        )
    )
    return int(row.scalar() or 0)


async def _revenue_in_window(
    db: AsyncSession,
    *,
    ozon_account_id: uuid.UUID,
    product_id: uuid.UUID,
    window_days: int,
) -> float:
    """Выручка по delivered заказам за окно (для ABC по выручке + ROI)."""
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    row = await db.execute(
        select(func.coalesce(func.sum(OrderItem.total_price), 0))
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.ozon_account_id == ozon_account_id,
            OrderItem.product_id == product_id,
            Order.status == "delivered",
            Order.order_created_at >= cutoff,
        )
    )
    return float(row.scalar() or 0)


async def _commission_in_window(
    db: AsyncSession,
    *,
    ozon_account_id: uuid.UUID,
    product_id: uuid.UUID,
    window_days: int,
) -> float:
    """SUM комиссии Ozon на delivered позициях за окно."""
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    row = await db.execute(
        select(func.coalesce(func.sum(OrderItem.commission), 0))
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.ozon_account_id == ozon_account_id,
            OrderItem.product_id == product_id,
            Order.status == "delivered",
            Order.order_created_at >= cutoff,
        )
    )
    return float(row.scalar() or 0)


# ============================================================
#  ОСНОВНОЙ СБОРЩИК — ProductRecommendation
# ============================================================


async def compute_product_recommendation(
    db: AsyncSession,
    product: Product,
    *,
    abc_class: str | None = None,
    abc_confidence: str | None = None,
    today: date_cls | None = None,
) -> dict[str, Any]:
    """Собирает полный набор рекомендаций для одного продукта.

    Возвращает dict (Pydantic-friendly) с buyout, velocity, procurement (None если
    нет supplier params), ROI (если есть себестоимость), и `missing_data`.
    """
    if today is None:
        today = datetime.now(UTC).date()

    # --- buyout (90 дней) ---
    delivered, cancelled, returned, arrived = await _gather_buyout_inputs(
        db,
        ozon_account_id=product.ozon_account_id,
        product_id=product.id,
        ozon_sku=product.ozon_sku,
        window_days=ForecastDefaults.BUYOUT_WINDOW_DAYS,
    )
    buyout = calc_buyout_rate(
        delivered=delivered,
        returned_after_delivery=returned,
        arrived_total=arrived,
        window_days=ForecastDefaults.BUYOUT_WINDOW_DAYS,
    )

    # --- velocity (28 дней) ---
    units, days_in, days_out = await _gather_velocity_inputs(
        db,
        ozon_account_id=product.ozon_account_id,
        product_id=product.id,
        window_days=ForecastDefaults.DAYS_IN_STOCK_WINDOW,
    )
    velocity = calc_velocity(
        total_units_sold=units,
        days_in_stock=days_in,
        days_out_of_stock=days_out,
        window=ForecastDefaults.DAYS_IN_STOCK_WINDOW,
    )

    # --- missing data flags ---
    missing_data: list[str] = []
    if product.cost_price is None:
        missing_data.append("Себестоимость не заполнена — нет валовой маржи и ROI")

    # --- current stock + in transit ---
    current_stock = await _current_stock_total(db, product.id)
    in_transit_to_customer = await _in_transit_to_customer(
        db, ozon_account_id=product.ozon_account_id, product_id=product.id
    )

    # --- procurement: читаем supply_params из БД, fallback на дефолты ---
    sp_row = await db.execute(
        select(ProductSupplyParams).where(ProductSupplyParams.product_id == product.id)
        .order_by(ProductSupplyParams.created_at.desc()).limit(1)
    )
    sp = sp_row.scalar_one_or_none()
    supply_params_set = sp is not None
    lead_time = sp.lead_time_total_days if sp else _DEFAULT_LEAD_TIME
    safety = sp.safety_stock_days if sp else _DEFAULT_SAFETY_STOCK
    moq = sp.moq if sp else _DEFAULT_MOQ
    batch_step = sp.batch_step if sp else _DEFAULT_BATCH_STEP
    batch_strict = sp.batch_strict if sp else _DEFAULT_BATCH_STRICT
    if not supply_params_set:
        missing_data.append(
            "Параметры поставки не заполнены — точка заказа использует дефолты "
            f"(lead_time={lead_time}, safety={safety} дней)"
        )

    # Учёт «груза в пути» от поставщика — SupplierOrder со статусом paid/in_transit
    in_transit_supplier_row = (await db.execute(text("""
        SELECT COALESCE(SUM(qty), 0) qty,
               MIN(expected_date) earliest_arrival
        FROM supplier_orders
        WHERE product_id = :pid AND status IN ('paid','in_transit')
    """), {"pid": str(product.id)})).first()
    in_transit_supplier = int(in_transit_supplier_row.qty or 0) if in_transit_supplier_row else 0
    earliest_arrival = in_transit_supplier_row.earliest_arrival if in_transit_supplier_row else None

    procurement_result = recommend_procurement(
        today=today,
        current_stock=current_stock,
        in_transit_from_supplier=in_transit_supplier,
        in_transit_from_customer=in_transit_to_customer,
        velocity=velocity,
        buyout=buyout,
        lead_time_total_days=lead_time,
        safety_stock_days=safety,
        moq=moq,
        batch_step=batch_step,
        batch_strict=batch_strict,
    )
    signal = _classify_reorder_signal(
        procurement_result.days_left, lead_time, safety
    )
    # Если есть «в пути» — статус "🚚 в пути" вместо «заказать»
    incoming_label: str | None = None
    if in_transit_supplier > 0:
        arr = earliest_arrival.isoformat() if earliest_arrival else None
        incoming_label = (
            f"🚚 в пути {in_transit_supplier} шт, прибудет {arr}" if arr
            else f"🚚 в пути {in_transit_supplier} шт"
        )
    # Hard override: физический остаток 0/1 — это всегда тревога, независимо от velocity.
    # Если скорости нет (товар не продаётся) — days_left=∞ → signal='ok', но 0/1 на складе
    # = «ничего не отгрузить если попросят», статус 'ok' вводит в заблуждение.
    if current_stock <= 0:
        signal = "stockout"
    elif current_stock <= 1 and signal == "ok":
        signal = "reorder_now"
    procurement: dict[str, Any] = asdict(procurement_result)
    procurement["signal"] = signal               # stockout / reorder_now / ok
    procurement["in_transit_supplier"] = in_transit_supplier
    procurement["earliest_arrival"] = earliest_arrival.isoformat() if earliest_arrival else None
    procurement["incoming_label"] = incoming_label
    procurement["lead_time_days"] = lead_time
    procurement["safety_stock_days"] = safety
    procurement["moq"] = moq
    procurement["supply_params_set"] = supply_params_set
    # Заменяем date-объекты на ISO-строки (Pydantic v2 их сериализует, но проще явно)
    if procurement.get("order_by"):
        procurement["order_by"] = procurement["order_by"].isoformat()
    if procurement.get("projected_stockout"):
        procurement["projected_stockout"] = procurement["projected_stockout"].isoformat()

    # --- ROI (если есть себестоимость) ---
    roi = None
    revenue_30d = await _revenue_in_window(
        db,
        ozon_account_id=product.ozon_account_id,
        product_id=product.id,
        window_days=30,
    )
    commission_30d = await _commission_in_window(
        db,
        ozon_account_id=product.ozon_account_id,
        product_id=product.id,
        window_days=30,
    )
    if product.cost_price is not None and units > 0:
        # ROI считаем грубо: profit_30d = revenue − cogs − commission
        # cogs = units_sold_30d × cost_price. Берём units из 30-дневного окна.
        # capital = current_stock × cost_price (что лежит на складе)
        cogs_30d = units * float(product.cost_price) * (30 / ForecastDefaults.DAYS_IN_STOCK_WINDOW)
        profit_30d = revenue_30d - cogs_30d - commission_30d
        capital = current_stock * float(product.cost_price)
        roi_result = calc_roi(
            profit_rub=profit_30d,
            invested_capital_rub=capital,
            period_days=30,
        )
        roi = asdict(roi_result)

    # --- worst_cluster: где у товара самый горящий регион ---
    worst_cluster = await _worst_cluster_for_product(
        db, ozon_account_id=product.ozon_account_id, product_id=product.id
    )

    # --- image_url из products.raw_data (как в /products endpoint) ---
    image_url = None
    raw = product.raw_data if isinstance(product.raw_data, dict) else None
    if raw:
        primary = raw.get("primary_image")
        if isinstance(primary, list):
            for item in primary:
                if isinstance(item, str) and item:
                    image_url = item
                    break
        elif isinstance(primary, str) and primary:
            image_url = primary

    # --- сборка ответа ---
    return {
        "product_id": str(product.id),
        "product_name": product.name,
        "offer_id": product.offer_id,
        "ozon_sku": product.ozon_sku,
        "current_price": float(product.current_price) if product.current_price is not None else None,
        "marketing_price": float(product.marketing_price) if product.marketing_price is not None else None,
        # selling_price = canonical "рабочая цена продавца", база финансов.
        # Берём marketing_seller_price (Ozon API → Product.marketing_price), а current_price (= Ozon `price`,
        # зачёркнутая 33000) — только fallback если СПП не синкнули.
        "selling_price": (
            float(product.marketing_price) if product.marketing_price is not None
            else (float(product.current_price) if product.current_price is not None else None)
        ),
        "sales_percent_fbo": float(product.sales_percent_fbo) if product.sales_percent_fbo is not None else None,
        "cost_price": float(product.cost_price) if product.cost_price is not None else None,
        "is_archived": bool(product.is_archived),
        "category_id": product.category_id,
        "category_name": product.category_name,
        "tags": product.tags or [],
        "is_hot": bool(product.is_hot),
        "image_url": image_url,
        "current_stock": current_stock,
        "in_transit_to_customer": in_transit_to_customer,
        "buyout": asdict(buyout),
        "velocity": asdict(velocity),
        "procurement": procurement,
        "roi_30d": roi,
        "abc_class": abc_class,
        "abc_confidence": abc_confidence,
        "missing_data": missing_data,
        "worst_cluster": worst_cluster,
    }


async def _worst_cluster_for_product(
    db: AsyncSession,
    *,
    ozon_account_id: uuid.UUID,
    product_id: uuid.UUID,
) -> dict[str, Any] | None:
    """Для UI: где у товара самый проблемный кластер.

    Берём latest FBO_WH snapshot, считаем velocity по cluster_from из orders 30д.
    Возвращаем кластер с минимальным days_left (или None если warehouse-данных нет).
    """
    latest_time = (await db.execute(
        select(func.max(Stock.time)).where(
            Stock.product_id == product_id, Stock.warehouse_type == "FBO_WH"
        )
    )).scalar()
    if not latest_time:
        return None

    rows = (await db.execute(
        select(Stock).where(
            Stock.product_id == product_id,
            Stock.warehouse_type == "FBO_WH",
            Stock.time == latest_time,
        )
    )).scalars().all()

    if not rows:
        return None

    # velocity per cluster_from
    cutoff = datetime.now(UTC) - timedelta(days=30)
    vel_rows = (await db.execute(
        select(
            Order.cluster_from,
            func.coalesce(func.sum(OrderItem.quantity), 0).label("qty"),
        )
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.ozon_account_id == ozon_account_id,
            OrderItem.product_id == product_id,
            Order.order_created_at >= cutoff,
            Order.status == "delivered",
            Order.cluster_from.is_not(None),
        )
        .group_by(Order.cluster_from)
    )).all()
    vel_map: dict[str, float] = {r.cluster_from: float(r.qty) / 30 for r in vel_rows}

    # Аггрегируем по кластерам (один кластер — несколько складов)
    cluster_stock: dict[str, int] = {}
    cluster_velocity: dict[str, float] = {}
    for s in rows:
        _, cluster = parse_warehouse_name(s.warehouse_name)
        if not cluster:
            continue
        cluster_stock[cluster] = cluster_stock.get(cluster, 0) + s.free_to_sell
        cluster_velocity[cluster] = cluster_velocity.get(cluster, 0) + vel_map.get(s.warehouse_name, 0)

    if not cluster_stock:
        return None

    # Worst = min days_left (или stockout/reorder_now)
    worst = None
    worst_days: float | None = None
    for cluster, stock in cluster_stock.items():
        v = cluster_velocity.get(cluster, 0.0)
        if stock <= 0:
            days_left = 0.0
        elif v <= 0:
            days_left = 99999.0  # неизвестно сколько хватит → не "плохой"
        else:
            days_left = stock / v
        if worst is None or (days_left < worst_days):
            worst_days = days_left
            worst = (cluster, stock, v, days_left)

    if not worst:
        return None
    cluster, stock, v, days_left = worst
    if stock <= 0:
        signal = "stockout"
    elif v > 0 and days_left < 7:
        signal = "reorder_now"
    else:
        signal = "ok"
    return {
        "cluster": cluster,
        "free_to_sell": stock,
        "velocity_per_day": round(v, 2),
        "days_left": round(days_left, 1) if days_left < 99999 else None,
        "signal": signal,
    }


# ============================================================
#  LIST: собирает рекомендации по всем продуктам компании
# ============================================================


async def compute_list_recommendations(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    cabinet_ids: list[uuid.UUID] | None = None,
) -> list[dict[str, Any]]:
    """Возвращает рекомендации для всех продуктов компании (с поправкой на
    фильтр кабинетов). ABC-класс считается ОДНОМОМЕНТНО для всех продуктов.
    """
    from app.models import OzonAccount

    q = (
        select(Product)
        .join(OzonAccount, OzonAccount.id == Product.ozon_account_id)
        .where(
            OzonAccount.company_id == company_id,
            OzonAccount.deleted_at.is_(None),
            Product.deleted_at.is_(None),
        )
    )
    if cabinet_ids:
        q = q.where(Product.ozon_account_id.in_(cabinet_ids))

    products = list((await db.execute(q)).scalars().all())
    if not products:
        return []

    # --- ABC по выручке: считаем revenue 30d для каждого, затем classify ---
    revenue_map: dict[uuid.UUID, float] = {}
    gross_map: dict[uuid.UUID, float] = {}
    for p in products:
        rev = await _revenue_in_window(
            db,
            ozon_account_id=p.ozon_account_id,
            product_id=p.id,
            window_days=30,
        )
        revenue_map[p.id] = rev
        if p.cost_price is not None:
            comm = await _commission_in_window(
                db,
                ozon_account_id=p.ozon_account_id,
                product_id=p.id,
                window_days=30,
            )
            # gross = revenue − cogs − commission (без logistics: пока нет)
            # cogs = (units_sold_30d) × cost_price
            units_row = await db.execute(
                select(func.coalesce(func.sum(OrderItem.quantity), 0))
                .select_from(OrderItem)
                .join(Order, Order.id == OrderItem.order_id)
                .where(
                    Order.ozon_account_id == p.ozon_account_id,
                    OrderItem.product_id == p.id,
                    Order.status == "delivered",
                    Order.order_created_at >= datetime.now(UTC) - timedelta(days=30),
                )
            )
            units30 = int(units_row.scalar() or 0)
            cogs = units30 * float(p.cost_price)
            gross_map[p.id] = max(0.0, rev - cogs - comm)

    abc = abc_classify_3axis(
        revenue_by_product=revenue_map,
        gross_by_product=gross_map if gross_map else None,
        net_by_product=None,  # требует OPEX, пока нет
    )

    # --- собираем по каждому продукту ---
    results: list[dict[str, Any]] = []
    for p in products:
        rec = await compute_product_recommendation(
            db,
            p,
            abc_class=abc.overall.get(p.id),
            abc_confidence=abc.confidence.get(p.id),
        )
        results.append(rec)

    return results
