"""
Alerts engine — генератор алертов на основе текущих данных.

При вызове `run_alerts(user_id)`:
1. Берёт все включенные AlertRule юзера
2. Для каждого типа выполняет проверку (низкий остаток, отрицательная маржа, и т.д.)
3. Если условие сработало — создаёт AlertHistory с dedup (тот же тип + entity за сегодня)
4. Возвращает количество новых алертов

Проверки опираются на уже существующие данные (warehouse_stocks, returns,
LoanPayment, transactions), без новых таблиц.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, UTC
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertHistory, AlertMarkerType, AlertRule, AlertSeverity


log = logging.getLogger(__name__)


_DEFAULT_THRESHOLDS: dict[str, dict[str, Any]] = {
    AlertMarkerType.STOCKOUT.value: {"days_left": 7},
    AlertMarkerType.OVERSTOCK.value: {"days_left": 180},
    AlertMarkerType.MARGIN_BELOW_MIN.value: {"min_pct": 10},
    AlertMarkerType.PRICE_BELOW_COST.value: {},
    AlertMarkerType.CREDIT_PAYMENT_DUE.value: {"days_before": 7},
    AlertMarkerType.NEGATIVE_REVIEW.value: {"rating_max": 3},
    AlertMarkerType.SALES_DROP.value: {"drop_pct": 30},
    AlertMarkerType.RETURN_RECEIVED.value: {"min_qty": 1},
}


def _today_dedupe(rule_type: str, entity: str) -> str:
    """dedup-ключ на день — на один alert одного типа на entity в сутки."""
    return f"{rule_type}::{entity}::{date.today().isoformat()}"


async def run_alerts(db: AsyncSession, user_id: uuid.UUID) -> dict[str, int]:
    """Запустить проверки правил юзера. Возвращает счётчики."""
    rules = (await db.execute(
        select(AlertRule).where(AlertRule.user_id == user_id, AlertRule.is_active == True)
    )).scalars().all()

    created = 0
    by_type: dict[str, int] = {}

    # company_id юзера (для запросов в transactions/loans)
    user_row = (await db.execute(text("SELECT company_id FROM users WHERE id = :u"),
                                  {"u": str(user_id)})).first()
    if not user_row:
        return {"total": 0, "by_type": {}}
    company_id = str(user_row.company_id)

    today = date.today()

    for rule in rules:
        rtype = rule.marker_type
        threshold = rule.threshold_json or _DEFAULT_THRESHOLDS.get(rtype, {})
        triggers: list[tuple[str, str, str]] = []  # (entity_key, label, message)

        # ----- STOCKOUT (низкий остаток по дням) -----
        if rtype == AlertMarkerType.STOCKOUT.value:
            days_left_th = float(threshold.get("days_left", 7))
            rows = (await db.execute(text("""
                SELECT p.id::text AS pid, p.name, p.offer_id,
                       SUM(ws.stock_for_sale) AS stock
                FROM warehouse_stocks ws
                JOIN products p ON p.id = ws.product_id
                JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
                WHERE oa.company_id = :cid AND ws.snapshot_date = (
                    SELECT MAX(snapshot_date) FROM warehouse_stocks
                )
                GROUP BY p.id, p.name, p.offer_id
                HAVING SUM(ws.stock_for_sale) <= :th
                LIMIT 50
            """), {"cid": company_id, "th": days_left_th * 5})).all()
            for r in rows:
                triggers.append((
                    r.pid, f"{r.name[:60]} ({r.offer_id})",
                    f"Остаток {int(r.stock)} шт ≤ порога — рискует кончиться за {days_left_th} дней",
                ))

        # ----- MARGIN_BELOW_MIN -----
        elif rtype == AlertMarkerType.MARGIN_BELOW_MIN.value:
            min_pct = float(threshold.get("min_pct", 10))
            rows = (await db.execute(text("""
                SELECT p.id::text AS pid, p.name, p.offer_id,
                       p.cost_price, p.marketing_seller_price
                FROM products p
                JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
                WHERE oa.company_id = :cid
                  AND p.cost_price IS NOT NULL
                  AND p.marketing_seller_price IS NOT NULL
                  AND p.marketing_seller_price > 0
                  AND ((p.marketing_seller_price - p.cost_price) / p.marketing_seller_price * 100) < :pct
                LIMIT 50
            """), {"cid": company_id, "pct": min_pct})).all()
            for r in rows:
                margin = (float(r.marketing_seller_price) - float(r.cost_price)) / float(r.marketing_seller_price) * 100
                triggers.append((
                    r.pid, f"{r.name[:60]} ({r.offer_id})",
                    f"Маржа {margin:.1f}% ниже минимума {min_pct}%",
                ))

        # ----- PRICE_BELOW_COST -----
        elif rtype == AlertMarkerType.PRICE_BELOW_COST.value:
            rows = (await db.execute(text("""
                SELECT p.id::text AS pid, p.name, p.offer_id,
                       p.cost_price, p.marketing_seller_price
                FROM products p
                JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
                WHERE oa.company_id = :cid
                  AND p.cost_price IS NOT NULL
                  AND p.marketing_seller_price IS NOT NULL
                  AND p.marketing_seller_price < p.cost_price
                LIMIT 50
            """), {"cid": company_id})).all()
            for r in rows:
                triggers.append((
                    r.pid, f"{r.name[:60]} ({r.offer_id})",
                    f"Цена {float(r.marketing_seller_price):.0f} ниже себестоимости {float(r.cost_price):.0f}",
                ))

        # ----- CREDIT_PAYMENT_DUE -----
        elif rtype == AlertMarkerType.CREDIT_PAYMENT_DUE.value:
            days_before = int(threshold.get("days_before", 7))
            rows = (await db.execute(text("""
                SELECT lp.id::text AS pid, l.lender, lp.pay_date,
                       (lp.principal_part + lp.interest_part + lp.fee_part) AS amount
                FROM loan_payments lp
                JOIN loans l ON l.id = lp.loan_id
                WHERE lp.company_id = :cid
                  AND lp.is_paid = false
                  AND lp.pay_date BETWEEN :today AND :horizon
                ORDER BY lp.pay_date
                LIMIT 50
            """), {"cid": company_id, "today": today,
                   "horizon": today + timedelta(days=days_before)})).all()
            for r in rows:
                triggers.append((
                    r.pid, f"{r.lender or 'кредит'} · {r.pay_date}",
                    f"Платёж {float(r.amount):.0f} ₽ через {(r.pay_date - today).days} дней",
                ))

        # ----- SALES_DROP (выручка за послед. 7 дней vs предыдущие 7) -----
        elif rtype == AlertMarkerType.SALES_DROP.value:
            drop_pct_th = float(threshold.get("drop_pct", 30))
            rows = (await db.execute(text("""
                WITH w AS (
                    SELECT oa.id AS account_id, oa.name,
                           SUM(t.amount) FILTER (
                               WHERE t.amount > 0 AND t.time >= NOW() - INTERVAL '7 days'
                           ) AS rev_cur,
                           SUM(t.amount) FILTER (
                               WHERE t.amount > 0
                                 AND t.time >= NOW() - INTERVAL '14 days'
                                 AND t.time < NOW() - INTERVAL '7 days'
                           ) AS rev_prev
                    FROM transactions t
                    JOIN ozon_accounts oa ON oa.id = t.ozon_account_id
                    WHERE oa.company_id = :cid
                      AND t.time >= NOW() - INTERVAL '14 days'
                    GROUP BY oa.id, oa.name
                )
                SELECT account_id::text, name, rev_cur, rev_prev
                FROM w
                WHERE rev_prev > 0
                  AND ((rev_prev - rev_cur) / rev_prev * 100) >= :pct
                LIMIT 20
            """), {"cid": company_id, "pct": drop_pct_th})).all()
            for r in rows:
                drop = (float(r.rev_prev) - float(r.rev_cur)) / float(r.rev_prev) * 100
                triggers.append((
                    r.account_id, f"{r.name}",
                    f"Выручка упала на {drop:.0f}% (было {float(r.rev_prev):.0f}₽ → стало {float(r.rev_cur):.0f}₽ за 7 дней)",
                ))

        # ----- CASHFLOW_GAP (DSCR < 1 в ближайшие 30 дней) -----
        elif rtype == AlertMarkerType.CASHFLOW_GAP.value:
            rows = (await db.execute(text("""
                WITH future_pay AS (
                    SELECT COALESCE(SUM(principal_part + interest_part + fee_part), 0) AS due
                    FROM loan_payments
                    WHERE company_id = :cid
                      AND is_paid = false
                      AND pay_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'
                ),
                hist_cf AS (
                    SELECT
                        COALESCE(SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END), 0)
                        - COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0)
                        AS net
                    FROM transactions t
                    JOIN ozon_accounts oa ON oa.id = t.ozon_account_id
                    WHERE oa.company_id = :cid
                      AND t.time >= NOW() - INTERVAL '30 days'
                )
                SELECT (SELECT due FROM future_pay) AS due,
                       (SELECT net FROM hist_cf) AS hist_net
            """), {"cid": company_id})).first()
            if rows and rows.due and float(rows.due) > 0:
                due = float(rows.due)
                hist = float(rows.hist_net or 0)
                if hist < due:
                    gap = due - hist
                    triggers.append((
                        "cashflow_30d",
                        f"Прогноз 30 дней",
                        f"Платежей по кредитам {due:.0f}₽, прогноз cashflow {hist:.0f}₽ — дыра {gap:.0f}₽",
                    ))

        # ----- NEGATIVE_REVIEW (если есть таблица reviews) -----
        elif rtype == AlertMarkerType.NEGATIVE_REVIEW.value:
            rmax = int(threshold.get("rating_max", 3))
            try:
                rows = (await db.execute(text("""
                    SELECT r.id::text AS pid, r.rating, p.name, p.offer_id,
                           r.created_at
                    FROM ozon_reviews r
                    LEFT JOIN products p ON p.id = r.product_id
                    JOIN ozon_accounts oa ON oa.id = r.ozon_account_id
                    WHERE oa.company_id = :cid
                      AND r.rating <= :rmax
                      AND r.created_at >= :df
                    LIMIT 50
                """), {"cid": company_id, "rmax": rmax,
                       "df": datetime.now(UTC) - timedelta(days=7)})).all()
                for r in rows:
                    triggers.append((
                        r.pid, f"{(r.name or 'товар')[:40]} ({r.offer_id or '—'})",
                        f"⭐ {r.rating} — за последние 7 дней",
                    ))
            except Exception:
                pass

        # Создаём AlertHistory с дедупом
        for entity_key, label, msg in triggers:
            dedupe = _today_dedupe(rtype, entity_key)
            exists = (await db.execute(text("""
                SELECT 1 FROM alerts_history
                WHERE user_id = :uid AND marker_type = :t
                  AND message = :m
                  AND triggered_at >= :today
                LIMIT 1
            """), {"uid": str(user_id), "t": rtype,
                   "m": f"[{label}] {msg}",
                   "today": datetime.combine(today, datetime.min.time())})).first()
            if exists:
                continue

            ah = AlertHistory(
                user_id=user_id,
                marker_type=rtype,
                ozon_account_id=rule.ozon_account_id,
                message=f"[{label}] {msg}",
                severity=AlertSeverity.WARNING.value,
            )
            db.add(ah)
            created += 1
            by_type[rtype] = by_type.get(rtype, 0) + 1

    await db.commit()
    return {"total": created, "by_type": by_type}


# Дефолтные правила для нового юзера / на init
DEFAULT_RULES = [
    {"marker_type": AlertMarkerType.STOCKOUT.value,
     "threshold_json": {"days_left": 7}, "channels_json": ["in_app"]},
    {"marker_type": AlertMarkerType.PRICE_BELOW_COST.value,
     "threshold_json": {}, "channels_json": ["in_app"]},
    {"marker_type": AlertMarkerType.MARGIN_BELOW_MIN.value,
     "threshold_json": {"min_pct": 10}, "channels_json": ["in_app"]},
    {"marker_type": AlertMarkerType.CREDIT_PAYMENT_DUE.value,
     "threshold_json": {"days_before": 7}, "channels_json": ["in_app"]},
    {"marker_type": AlertMarkerType.SALES_DROP.value,
     "threshold_json": {"drop_pct": 30}, "channels_json": ["in_app"]},
    {"marker_type": AlertMarkerType.CASHFLOW_GAP.value,
     "threshold_json": {}, "channels_json": ["in_app"]},
]


async def seed_default_rules(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Создать дефолтные правила, если их ещё нет."""
    existing = {r.marker_type for r in (await db.execute(
        select(AlertRule).where(AlertRule.user_id == user_id)
    )).scalars().all()}
    created = 0
    for r in DEFAULT_RULES:
        if r["marker_type"] in existing:
            continue
        db.add(AlertRule(
            user_id=user_id,
            marker_type=r["marker_type"],
            threshold_json=r["threshold_json"],
            channels_json=r["channels_json"],
            is_active=True,
        ))
        created += 1
    await db.commit()
    return created
