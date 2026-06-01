"""
Backfill order_items.customer_price из customer_price_monthly_estimate.

#105: для старых месяцев posting/fbo/get >90 дней не отдаёт, точный
customer_price невозможен. Берём weighted_avg за месяц по SKU из realization
(уже посчитано sync_realization), проставляем как oценку с
customer_price_source='estimated_monthly'.

Только NULL-записи перезаписываются — точные customer_price из
posting/fbo/get (source IS NULL = свежие) НЕ трогаем.
"""
from __future__ import annotations

from celery import shared_task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.workers.tasks._helpers import run_celery_async


@shared_task(name="backfill_customer_price_estimate", bind=True)
def backfill_customer_price_estimate(self) -> dict:
    return run_celery_async(_run)


async def _run(SessionLocal: async_sessionmaker[AsyncSession]) -> dict:
    """
    Для каждой пары (cabinet, sku, month) из customer_price_monthly_estimate:
    UPDATE order_items SET customer_price = weighted_cp,
                            customer_price_source = 'estimated_monthly'
    WHERE customer_price IS NULL AND ozon_sku = sku
      AND order_created_at в месяце.

    Не перезаписывает существующие точные значения.
    """
    async with SessionLocal() as db:
        # Один UPDATE который проходит по всей таблице оценок
        result = await db.execute(text("""
            UPDATE order_items oi
            SET customer_price = est.weighted_cp,
                customer_price_source = 'estimated_monthly'
            FROM customer_price_monthly_estimate est
            JOIN orders o ON o.ozon_account_id = est.cabinet_id
            WHERE oi.order_id = o.id
              AND oi.ozon_sku = est.sku
              AND o.order_created_at >= est.month
              AND o.order_created_at < (est.month + INTERVAL '1 month')
              AND oi.customer_price IS NULL
        """))
        await db.commit()
        updated = result.rowcount or 0

        # Статистика покрытия после backfill
        coverage = (await db.execute(text("""
            SELECT
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE customer_price IS NOT NULL) AS with_cp,
              COUNT(*) FILTER (WHERE customer_price_source = 'estimated_monthly') AS from_estimate,
              COUNT(*) FILTER (WHERE customer_price IS NOT NULL
                               AND (customer_price_source IS NULL OR customer_price_source = 'api')) AS exact
            FROM order_items
        """))).one()

        log.info(
            "customer_price_backfilled",
            updated=updated,
            total=coverage.total,
            with_cp=coverage.with_cp,
            from_estimate=coverage.from_estimate,
            exact=coverage.exact,
            pct=round(100.0 * coverage.with_cp / max(coverage.total, 1), 2),
        )

        return {
            "updated_rows": updated,
            "total_items": coverage.total,
            "with_customer_price": coverage.with_cp,
            "from_estimate": coverage.from_estimate,
            "exact_from_api": coverage.exact,
            "coverage_pct": round(100.0 * coverage.with_cp / max(coverage.total, 1), 2),
        }
