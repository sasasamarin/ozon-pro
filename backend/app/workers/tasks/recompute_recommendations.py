"""
Nightly batch: пересчёт SalesVelocityCache по всем продуктам.

Зачем: API `/recommendations` сейчас считает на лету за 10-30 секунд (N
агрегатов × M продуктов). При росте до 100+ продуктов это станет дорого.
Кэш в SalesVelocityCache (hypertable) даёт O(1)-чтение в UI, а тяжёлый
расчёт делает фоновый воркер раз в сутки.

Текущая стадия — есть данные за 17 месяцев, но cost_price/supply_params
ещё не заполнены. Кэш пишет: velocity longterm/shortterm + trend_signal +
recommended_daily + базу для UI («почему такая рекомендация»). Полную
рекомендацию закупки добавим когда юзер заполнит лead_time/MOQ/safety_stock.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.logging import log
from app.models import Order, OrderItem, OzonAccount, Product, Stock
from app.models.procurement import SalesVelocityCache, TrendSignal
from app.services.forecasting import ForecastDefaults
from app.services.forecasting.velocity import calc_velocity
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import run_celery_async


@celery_app.task(name="app.workers.tasks.recompute_recommendations.recompute_all")
def recompute_all_recommendations() -> dict:
    """Пересчёт velocity-кэша по всем продуктам всех активных кабинетов."""
    return run_celery_async(_recompute_all_async)


async def _recompute_all_async(SessionLocal: async_sessionmaker) -> dict:
    async with SessionLocal() as db:
        accounts = list(
            (
                await db.execute(
                    select(OzonAccount).where(
                        OzonAccount.is_active.is_(True),
                        OzonAccount.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )

        total_processed = 0
        total_skipped = 0
        per_account: dict[str, dict] = {}

        for acc in accounts:
            stats = {"processed": 0, "skipped": 0}
            products = list(
                (
                    await db.execute(
                        select(Product).where(
                            Product.ozon_account_id == acc.id,
                            Product.deleted_at.is_(None),
                            Product.is_archived.is_(False),
                        )
                    )
                )
                .scalars()
                .all()
            )

            for product in products:
                row = await _compute_velocity_row(
                    db, account_id=acc.id, user_id=acc.user_id, product=product
                )
                if row is None:
                    stats["skipped"] += 1
                    continue

                # Idempotent upsert: PK = (time, product_id) → ON CONFLICT DO UPDATE
                stmt = insert(SalesVelocityCache).values(**row)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["time", "product_id"],
                    set_={k: v for k, v in row.items() if k not in {"time", "product_id"}},
                )
                await db.execute(stmt)
                stats["processed"] += 1

            await db.commit()
            per_account[str(acc.id)] = stats
            total_processed += stats["processed"]
            total_skipped += stats["skipped"]

            log.info(
                "recompute_recommendations_account_done",
                account_id=str(acc.id),
                account_name=acc.name,
                **stats,
            )

        return {
            "total_processed": total_processed,
            "total_skipped": total_skipped,
            "per_account": per_account,
        }


async def _compute_velocity_row(db, *, account_id, user_id, product: Product) -> dict | None:
    """Считает velocity longterm (365д) + shortterm (14д) + trend_signal → dict
    для UPSERT в SalesVelocityCache. Возвращает None если нет данных вообще.
    """
    now = datetime.now(UTC)

    # --- longterm 365 дней ---
    longterm_window = 365
    units_long = await _units_in_window(db, account_id, product.id, longterm_window)
    days_in_long = await _days_in_stock_in_window(db, product.id, longterm_window)

    if units_long == 0 and days_in_long == 0:
        return None  # совсем пусто, не пишем мусор

    v_long = calc_velocity(
        total_units_sold=units_long,
        days_in_stock=days_in_long,
        days_out_of_stock=max(0, longterm_window - days_in_long),
        window=longterm_window,
    )

    # --- shortterm 14 дней ---
    shortterm_window = 14
    units_short = await _units_in_window(db, account_id, product.id, shortterm_window)
    days_in_short = await _days_in_stock_in_window(db, product.id, shortterm_window)

    v_short = calc_velocity(
        total_units_sold=units_short,
        days_in_stock=days_in_short,
        days_out_of_stock=max(0, shortterm_window - days_in_short),
        window=shortterm_window,
    )

    # --- trend signal ---
    ratio = None
    signal = TrendSignal.STABLE.value
    if v_long.adjusted_daily > 0:
        ratio = v_short.adjusted_daily / v_long.adjusted_daily
        if ratio >= ForecastDefaults.TREND_RISING:
            signal = TrendSignal.RISING.value
        elif ratio <= ForecastDefaults.TREND_FALLING:
            signal = TrendSignal.FALLING.value
        elif abs(ratio - 1) > ForecastDefaults.VOLATILE_CV:
            signal = TrendSignal.VOLATILE.value

    # --- recommended_daily: longterm с поправкой на тренд ---
    if signal == TrendSignal.RISING.value:
        recommended = (v_long.adjusted_daily + v_short.adjusted_daily) / 2
    elif signal == TrendSignal.FALLING.value:
        recommended = v_long.adjusted_daily * 0.9
    else:
        recommended = v_long.adjusted_daily

    return {
        "time": now,
        "product_id": product.id,
        "ozon_account_id": account_id,
        "user_id": user_id,
        "longterm_window_days": longterm_window,
        "longterm_avg_daily": v_long.raw_avg_daily,
        "longterm_seasonal_factor": 1.0,  # TODO: подмешать seasonality.combined_seasonal_factor
        "longterm_adjusted_daily": v_long.adjusted_daily,
        "longterm_confidence": v_long.confidence,
        "shortterm_window_days": shortterm_window,
        "shortterm_avg_daily": v_short.adjusted_daily,
        "trend_ratio": ratio,
        "trend_signal": signal,
        "recommended_daily": recommended,
        "recommendation_basis": v_long.basis,
        "total_units_sold": units_long,
        "days_in_stock": days_in_long,
        "days_out_of_stock": max(0, longterm_window - days_in_long),
        "calculated_at": now,
    }


async def _units_in_window(db, account_id, product_id, window_days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    row = await db.execute(
        select(func.coalesce(func.sum(OrderItem.quantity), 0))
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.ozon_account_id == account_id,
            OrderItem.product_id == product_id,
            Order.order_created_at >= cutoff,
        )
    )
    return int(row.scalar() or 0)


async def _days_in_stock_in_window(db, product_id, window_days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    row = await db.execute(
        select(func.count(func.distinct(func.date_trunc("day", Stock.time)))).where(
            Stock.product_id == product_id,
            Stock.time >= cutoff,
            Stock.free_to_sell > 0,
        )
    )
    return int(row.scalar() or 0)
