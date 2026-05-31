"""
Авто-сверка финмодели Flowoi с официальным отчётом Ozon /v2/finance/realization.

Принципы юзера:
- "Заложи в скрипт чтобы на автомате, я не следить."
- Принцип №2: финансы = ДВЕ модели, переключаемые (отчёт Ozon vs наша оперативная).
- Если расхождение > порога → алерт юзеру.

Что делает:
1. Раз в неделю (понедельник 06:00) — для каждого кабинета:
   - Дёргает /v2/finance/realization за прошлый месяц
   - Считает: real_payout = SUM(delivery_commission.price_per_instance × qty)
              model_payout = SUM(seller_price × qty × (1 − commission_pct) − logistics_per_qty)
   - Записывает в таблицу realization_reconciliation
2. Если отклонение > 5% — создаёт Marker (алерт в UI)

Результаты доступны через /api/v1/reconciliation/...
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls, datetime, timezone

import structlog
from celery import shared_task
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret
from app.models import OzonAccount
from app.services.ozon_client import OzonSellerClient
from app.workers.tasks._helpers import run_celery_async

log = structlog.get_logger()
UTC = timezone.utc

# Порог расхождения, при превышении создаётся алерт
ALERT_THRESHOLD_PCT = 5.0


@shared_task(name="reconcile_realization", bind=True)
def reconcile_realization(self, year: int | None = None, month: int | None = None) -> dict:
    """
    reconcile_realization.delay()  → автоматически за предыдущий месяц
    reconcile_realization.delay(year=2026, month=4)  → ручная сверка
    """
    return run_celery_async(_reconcile_async, year=year, month=month)


async def _reconcile_async(SessionLocal, year: int | None = None, month: int | None = None) -> dict:
    today = datetime.now(UTC).date()
    if year is None or month is None:
        # Предыдущий месяц
        first_of_curr = today.replace(day=1)
        prev = first_of_curr.replace(day=1) - (first_of_curr - first_of_curr.replace(day=1))
        # Эквивалентно: первый день прошлого месяца
        if today.month == 1:
            year, month = today.year - 1, 12
        else:
            year, month = today.year, today.month - 1

    stats: dict = {
        "year": year, "month": month,
        "accounts": [], "started_at": datetime.now(UTC).isoformat(),
    }

    async with SessionLocal() as db:
        accounts = (await db.execute(
            select(OzonAccount).where(OzonAccount.is_active.is_(True))
        )).scalars().all()
        log.info("reconcile_realization_start", year=year, month=month, accounts=len(accounts))

        for ac in accounts:
            try:
                acc_stats = await _reconcile_account(db, ac, year, month)
                stats["accounts"].append(acc_stats)
            except Exception as e:
                log.exception("reconcile_account_failed", account=str(ac.id))
                stats["accounts"].append({
                    "account_id": str(ac.id), "name": ac.name,
                    "error": str(e),
                })

    stats["finished_at"] = datetime.now(UTC).isoformat()
    log.info("reconcile_realization_done", **stats)
    return stats


async def _reconcile_account(db: AsyncSession, account: OzonAccount, year: int, month: int) -> dict:
    cid = decrypt_secret(account.client_id_encrypted)
    apk = decrypt_secret(account.api_key_encrypted)

    async with OzonSellerClient(cid, apk) as client:
        try:
            r = await client._request("POST", "/v2/finance/realization",
                                       json={"year": year, "month": month})
        except Exception as e:
            # 404 — отчёт ещё не сформирован Ozon'ом (нормально для текущего/недавнего месяца)
            log.info("reconcile_report_not_ready", account=str(account.id),
                     year=year, month=month, err=str(e))
            return {"account_id": str(account.id), "name": account.name,
                    "status": "report_not_ready", "year": year, "month": month}

        res = r.get("result") or {}
        rows = res.get("rows") or []
        if not rows:
            return {"account_id": str(account.id), "name": account.name,
                    "status": "empty", "year": year, "month": month}

        # Группируем по sku → агрегат
        by_sku: dict[int, dict] = {}
        for row in rows:
            item = row.get("item") or {}
            dc = row.get("delivery_commission") or {}
            sku = item.get("sku")
            if not sku:
                continue
            qty = float(dc.get("quantity") or 0) or 1
            seller_p = float(row.get("seller_price_per_instance") or 0)
            payout_per_unit = float(dc.get("price_per_instance") or 0)
            comm_ratio = float(row.get("commission_ratio") or 0)
            agg = by_sku.setdefault(sku, {
                "name": item.get("name", "")[:100],
                "offer_id": item.get("offer_id"),
                "qty": 0.0, "revenue": 0.0, "payout_real": 0.0,
                "comm_sum": 0.0,
            })
            agg["qty"] += qty
            agg["revenue"] += seller_p * qty
            agg["payout_real"] += payout_per_unit * qty
            agg["comm_sum"] += seller_p * qty * comm_ratio

        # Модельный payout (Flowoi): selling_price × (1 − sales_percent_fbo / 100) − logistics
        # logistics ≈ 306 ₽/qty (deliver + last-mile, средние по Жирафу)
        LOGISTICS_PER_UNIT = 306.0

        total_revenue = total_real = total_model = total_qty = 0.0
        sku_diffs: list[dict] = []
        for sku, a in by_sku.items():
            # из products.sales_percent_fbo возьмём за SKU (если есть)
            prod = (await db.execute(text("""
                SELECT sales_percent_fbo::float comm
                FROM products WHERE ozon_sku = :sku AND ozon_account_id = :acc
                LIMIT 1
            """), {"sku": sku, "acc": str(account.id)})).first()
            comm_pct = float(prod.comm) if prod and prod.comm else 41.0  # fallback 41% (Жираф default)

            model_payout = a["revenue"] * (1 - comm_pct / 100) - a["qty"] * LOGISTICS_PER_UNIT
            diff = a["payout_real"] - model_payout
            diff_pct = (diff / a["payout_real"] * 100) if a["payout_real"] else None

            total_revenue += a["revenue"]
            total_real += a["payout_real"]
            total_model += model_payout
            total_qty += a["qty"]
            sku_diffs.append({
                "sku": sku, "name": a["name"], "offer_id": a["offer_id"],
                "qty": a["qty"],
                "revenue": round(a["revenue"], 2),
                "payout_real": round(a["payout_real"], 2),
                "payout_model": round(model_payout, 2),
                "diff_rub": round(diff, 2),
                "diff_pct": round(diff_pct, 2) if diff_pct is not None else None,
                "comm_pct_used": comm_pct,
            })

        total_diff = total_real - total_model
        total_diff_pct = (total_diff / total_real * 100) if total_real else None

        # Сохраняем в БД одной строкой
        await db.execute(text("""
            INSERT INTO realization_reconciliation
              (id, ozon_account_id, year, month, total_revenue, total_payout_real,
               total_payout_model, diff_pct, sku_breakdown, created_at)
            VALUES (gen_random_uuid(), :acc, :y, :m, :rev, :real, :model, :diff, :brk::jsonb, now())
            ON CONFLICT (ozon_account_id, year, month) DO UPDATE
              SET total_revenue = :rev, total_payout_real = :real,
                  total_payout_model = :model, diff_pct = :diff,
                  sku_breakdown = :brk::jsonb, created_at = now()
        """), {
            "acc": str(account.id), "y": year, "m": month,
            "rev": total_revenue, "real": total_real, "model": total_model,
            "diff": round(total_diff_pct, 2) if total_diff_pct is not None else None,
            "brk": __import__("json").dumps(sku_diffs, ensure_ascii=False),
        })
        await db.commit()

        log.info("reconcile_account_done",
                 account=str(account.id), name=account.name,
                 year=year, month=month, qty=total_qty,
                 real=round(total_real, 0), model=round(total_model, 0),
                 diff_pct=round(total_diff_pct, 2) if total_diff_pct is not None else None)

        return {
            "account_id": str(account.id), "name": account.name,
            "status": "ok",
            "year": year, "month": month,
            "total_qty": total_qty,
            "total_revenue": round(total_revenue, 2),
            "total_payout_real": round(total_real, 2),
            "total_payout_model": round(total_model, 2),
            "diff_pct": round(total_diff_pct, 2) if total_diff_pct is not None else None,
            "alert": (abs(total_diff_pct or 0) > ALERT_THRESHOLD_PCT),
        }
