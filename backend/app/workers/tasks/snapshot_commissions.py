"""
Ежедневный snapshot комиссий per-SKU. Для COMMISSION_CHANGE алерта.

Запуск через celery beat — раз в день после sync-products.
Записывает в product_commission_history только при ИЗМЕНЕНИИ комиссии
относительно последней записи — экономит место.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.models import Product, ProductCommissionHistory
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import run_celery_async


@celery_app.task(name="app.workers.tasks.snapshot_commissions.snapshot_all")
def snapshot_all() -> dict:
    """Снять snapshot комиссий для всех products."""
    return run_celery_async(_run_async)


async def _run_async(SessionLocal: async_sessionmaker[AsyncSession]) -> dict:
    async with SessionLocal() as db:
        today = date.today()

        # Берём только товары с комиссиями
        prods = (await db.execute(
            select(Product.id, Product.sales_percent_fbo, Product.sales_percent_fbs)
            .where(Product.sales_percent_fbo.is_not(None))
        )).all()

        if not prods:
            return {"products": 0, "snapshots_added": 0}

        # Последние snapshot-ы (для diff)
        last_rows = (await db.execute(text("""
            SELECT DISTINCT ON (product_id)
                   product_id::text AS pid,
                   sales_percent_fbo, sales_percent_fbs
            FROM product_commission_history
            ORDER BY product_id, snapshot_date DESC
        """))).all()
        last_by_pid = {
            r.pid: (float(r.sales_percent_fbo or 0), float(r.sales_percent_fbs or 0))
            for r in last_rows
        }

        added = 0
        for p in prods:
            pid_str = str(p.id)
            cur = (float(p.sales_percent_fbo or 0), float(p.sales_percent_fbs or 0))
            last = last_by_pid.get(pid_str)
            if last == cur:
                continue  # без изменений — не пишем

            # Upsert today snapshot
            await db.execute(text("""
                INSERT INTO product_commission_history
                    (product_id, snapshot_date, sales_percent_fbo, sales_percent_fbs)
                VALUES (:pid, :dt, :fbo, :fbs)
                ON CONFLICT (product_id, snapshot_date) DO UPDATE SET
                    sales_percent_fbo = EXCLUDED.sales_percent_fbo,
                    sales_percent_fbs = EXCLUDED.sales_percent_fbs
            """), {"pid": pid_str, "dt": today,
                   "fbo": cur[0], "fbs": cur[1]})
            added += 1

        await db.commit()
        log.info("commission_snapshots", products=len(prods), added=added)
        return {"products": len(prods), "snapshots_added": added}
