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
    AlertMarkerType.OVERSTOCK.value: {"days_coverage": 180},
    AlertMarkerType.MARGIN_BELOW_MIN.value: {"min_pct": 10},
    AlertMarkerType.PRICE_BELOW_COST.value: {},
    AlertMarkerType.CREDIT_PAYMENT_DUE.value: {"days_before": 7},
    AlertMarkerType.NEGATIVE_REVIEW.value: {"rating_max": 3},
    AlertMarkerType.SALES_DROP.value: {"drop_pct": 30},
    AlertMarkerType.RETURN_RECEIVED.value: {"min_qty": 1},
    AlertMarkerType.FBS_NOT_SHIPPED.value: {"hours_threshold": 24},
    AlertMarkerType.TAX_DUE.value: {"days_before": 14},
    AlertMarkerType.RATING_DROP.value: {"min_rating": 4.5},
    AlertMarkerType.AD_BUDGET_EXCEEDED.value: {"drr_pct_max": 25},
    AlertMarkerType.POSITION_DROP.value: {"position_drop": 5},
    AlertMarkerType.LOW_CONVERSION.value: {"min_pct": 5},
    AlertMarkerType.COMPETITOR_DUMP.value: {},
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

        # ----- OVERSTOCK (избыток — товара на > N дней покрытия) -----
        elif rtype == AlertMarkerType.OVERSTOCK.value:
            days_th = float(threshold.get("days_coverage", 180))
            rows = (await db.execute(text("""
                WITH sales AS (
                    SELECT oi.product_id,
                           COUNT(*)::float / NULLIF(EXTRACT(EPOCH FROM (NOW() - NOW() + INTERVAL '30 days')) / 86400, 0)
                             AS daily_sales
                    FROM order_items oi
                    JOIN orders o ON o.id = oi.order_id
                    JOIN ozon_accounts oa ON oa.id = o.ozon_account_id
                    WHERE oa.company_id = :cid
                      AND o.created_at >= NOW() - INTERVAL '30 days'
                      AND o.status = 'delivered'
                    GROUP BY oi.product_id
                ),
                stocks AS (
                    SELECT ws.product_id, SUM(ws.stock_for_sale) AS stock
                    FROM warehouse_stocks ws
                    WHERE ws.snapshot_date = (SELECT MAX(snapshot_date) FROM warehouse_stocks)
                    GROUP BY ws.product_id
                )
                SELECT p.id::text AS pid, p.name, p.offer_id,
                       COALESCE(s.stock, 0) AS stock,
                       s.stock / NULLIF(sl.daily_sales, 0) AS days_cov
                FROM products p
                JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
                LEFT JOIN stocks s ON s.product_id = p.id
                LEFT JOIN sales sl ON sl.product_id = p.id
                WHERE oa.company_id = :cid
                  AND COALESCE(s.stock, 0) > 0
                  AND sl.daily_sales > 0
                  AND (s.stock / NULLIF(sl.daily_sales, 0)) > :th
                ORDER BY days_cov DESC
                LIMIT 30
            """), {"cid": company_id, "th": days_th})).all()
            for r in rows:
                cov = float(r.days_cov or 0)
                triggers.append((
                    r.pid, f"{r.name[:60]} ({r.offer_id})",
                    f"Остаток {int(r.stock)} шт на {cov:.0f} дней — порог {days_th:.0f} дней",
                ))

        # ----- FBS_NOT_SHIPPED (заказы FBS не отгружены > N часов) -----
        elif rtype == AlertMarkerType.FBS_NOT_SHIPPED.value:
            hours_th = int(threshold.get("hours_threshold", 24))
            rows = (await db.execute(text("""
                SELECT o.id::text AS oid, o.posting_number, o.created_at,
                       EXTRACT(EPOCH FROM (NOW() - o.created_at)) / 3600 AS hours_open
                FROM orders o
                JOIN ozon_accounts oa ON oa.id = o.ozon_account_id
                WHERE oa.company_id = :cid
                  AND o.order_type = 'fbs'
                  AND o.status IN ('awaiting_packaging', 'awaiting_deliver', 'acceptance_in_progress')
                  AND o.created_at < NOW() - (:hours || ' hours')::interval
                LIMIT 50
            """), {"cid": company_id, "hours": hours_th})).all()
            for r in rows:
                triggers.append((
                    r.oid, f"posting {r.posting_number}",
                    f"FBS не отгружен {float(r.hours_open):.0f}ч (порог {hours_th}ч)",
                ))

        # ----- TAX_DUE (квартальные сроки УСН) -----
        elif rtype == AlertMarkerType.TAX_DUE.value:
            days_before = int(threshold.get("days_before", 14))
            # Сроки квартальных авансов: 28 апр, 28 июл, 28 окт; годовой 28 марта
            tax_dates = [
                (3, 28, "годовой налог"),
                (4, 28, "аванс за Q1"),
                (7, 28, "аванс за Q2"),
                (10, 28, "аванс за Q3"),
            ]
            from datetime import date as _d
            today = _d.today()
            for month, day, label in tax_dates:
                tax_date = _d(today.year, month, day)
                diff = (tax_date - today).days
                if 0 <= diff <= days_before:
                    triggers.append((
                        f"tax_{month}_{day}", label,
                        f"Срок уплаты ({tax_date.isoformat()}) — через {diff} дней",
                    ))

        # ----- RATING_DROP (средний рейтинг товара < порога) -----
        elif rtype == AlertMarkerType.RATING_DROP.value:
            min_rating = float(threshold.get("min_rating", 4.5))
            try:
                rows = (await db.execute(text("""
                    SELECT p.id::text AS pid, p.name, p.offer_id,
                           p.rating
                    FROM products p
                    JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
                    WHERE oa.company_id = :cid
                      AND p.rating IS NOT NULL
                      AND p.rating < :th
                    ORDER BY p.rating ASC
                    LIMIT 30
                """), {"cid": company_id, "th": min_rating})).all()
                for r in rows:
                    triggers.append((
                        r.pid, f"{r.name[:60]} ({r.offer_id})",
                        f"Рейтинг {float(r.rating):.2f} ниже порога {min_rating}",
                    ))
            except Exception:
                pass

        # ----- COMPETITOR_DUMP (color_index=RED у наших SKU) -----
        elif rtype == AlertMarkerType.COMPETITOR_DUMP.value:
            try:
                from app.models import OzonAccount
                from app.core.security import decrypt_secret
                from app.services.ozon_client import OzonSellerClient

                accs = (await db.execute(
                    select(OzonAccount).where(
                        OzonAccount.company_id == company_id,
                        OzonAccount.deleted_at.is_(None),
                    )
                )).scalars().all()

                red_items = []
                for acc in accs:
                    if rule.ozon_account_id and acc.id != rule.ozon_account_id:
                        continue
                    cid = decrypt_secret(acc.client_id_encrypted)
                    apk = decrypt_secret(acc.api_key_encrypted)
                    async with OzonSellerClient(cid, apk) as client:
                        try:
                            r = await client._request(
                                "POST", "/v5/product/info/prices",
                                json={"filter": {"product_id": [], "visibility": "ALL"},
                                      "limit": 100, "cursor": ""},
                            )
                        except Exception:
                            continue
                        for it in (r.get("items") or []):
                            idx = (it.get("price_indexes") or {})
                            if idx.get("color_index") == "RED":
                                ext = (idx.get("external_index_data") or {})
                                ext_min = float(ext.get("min_price") or 0)
                                price = float((it.get("price") or {}).get("marketing_seller_price") or 0)
                                red_items.append((
                                    str(it.get("product_id")),
                                    it.get("offer_id") or "",
                                    price, ext_min,
                                ))
                for pid, offer, price, ext_min in red_items[:30]:
                    delta_pct = ((price - ext_min) / ext_min * 100) if ext_min > 0 else 0
                    triggers.append((
                        pid, f"{offer}",
                        f"Конкуренты демпингуют: внешн.мин {ext_min:.0f}₽ vs наша {price:.0f}₽ (+{delta_pct:.0f}%)",
                    ))
            except Exception:
                pass

        # ----- POSITION_DROP (средняя позиция за 7д упала vs предыдущие 7д) -----
        elif rtype == AlertMarkerType.POSITION_DROP.value:
            drop_th = int(threshold.get("position_drop", 5))
            try:
                rows = (await db.execute(text("""
                    WITH p AS (
                        SELECT pq.product_id, p.name, p.offer_id,
                               AVG(CASE WHEN pq.date >= CURRENT_DATE - INTERVAL '7 days'
                                        THEN pq.position END) AS pos_cur,
                               AVG(CASE WHEN pq.date >= CURRENT_DATE - INTERVAL '14 days'
                                        AND pq.date < CURRENT_DATE - INTERVAL '7 days'
                                        THEN pq.position END) AS pos_prev
                        FROM product_queries_daily pq
                        JOIN ozon_accounts oa ON oa.id = pq.cabinet_id
                        JOIN products p ON p.id = pq.product_id
                        WHERE oa.company_id = :cid
                          AND pq.date >= CURRENT_DATE - INTERVAL '14 days'
                          AND pq.position IS NOT NULL
                        GROUP BY pq.product_id, p.name, p.offer_id
                    )
                    SELECT product_id::text AS pid, name, offer_id, pos_cur, pos_prev
                    FROM p
                    WHERE pos_cur IS NOT NULL AND pos_prev IS NOT NULL
                      AND (pos_cur - pos_prev) >= :th
                    ORDER BY (pos_cur - pos_prev) DESC
                    LIMIT 20
                """), {"cid": company_id, "th": drop_th})).all()
                for r in rows:
                    delta = float(r.pos_cur) - float(r.pos_prev)
                    triggers.append((
                        r.pid, f"{r.name[:60]} ({r.offer_id})",
                        f"Позиция упала с {float(r.pos_prev):.1f} до {float(r.pos_cur):.1f} (+{delta:.1f})",
                    ))
            except Exception:
                pass

        # ----- LOW_CONVERSION (карточка → корзина ниже порога) -----
        elif rtype == AlertMarkerType.LOW_CONVERSION.value:
            min_conv = float(threshold.get("min_pct", 5))
            try:
                rows = (await db.execute(text("""
                    SELECT pq.product_id::text AS pid, p.name, p.offer_id,
                           AVG(pq.view_conversion) * 100 AS conv_pct
                    FROM product_queries_daily pq
                    JOIN ozon_accounts oa ON oa.id = pq.cabinet_id
                    JOIN products p ON p.id = pq.product_id
                    WHERE oa.company_id = :cid
                      AND pq.date >= CURRENT_DATE - INTERVAL '7 days'
                      AND pq.view_conversion IS NOT NULL
                      AND pq.unique_view_users > 50
                    GROUP BY pq.product_id, p.name, p.offer_id
                    HAVING AVG(pq.view_conversion) * 100 < :th
                    ORDER BY conv_pct
                    LIMIT 20
                """), {"cid": company_id, "th": min_conv})).all()
                for r in rows:
                    triggers.append((
                        r.pid, f"{r.name[:60]} ({r.offer_id})",
                        f"Конверсия в корзину {float(r.conv_pct):.2f}% ниже {min_conv}%",
                    ))
            except Exception:
                pass

        # ----- AD_BUDGET_EXCEEDED (ДРР > порога за последние 30 дней) -----
        elif rtype == AlertMarkerType.AD_BUDGET_EXCEEDED.value:
            drr_max = float(threshold.get("drr_pct_max", 25))
            try:
                row = (await db.execute(text("""
                    SELECT
                        COALESCE(SUM(ABS(t.advertising)), 0)::float AS ad,
                        COALESCE(SUM(t.accruals_for_sale) FILTER (
                            WHERE t.operation_type='OperationAgentDeliveredToCustomer'
                        ), 0)::float AS rev
                    FROM transactions t
                    JOIN ozon_accounts oa ON oa.id = t.ozon_account_id
                    WHERE oa.company_id = :cid
                      AND t.time >= NOW() - INTERVAL '30 days'
                """), {"cid": company_id})).first()
                if row and float(row.rev or 0) > 0:
                    drr = float(row.ad or 0) / float(row.rev) * 100
                    if drr > drr_max:
                        triggers.append((
                            "drr_30d", "Реклама",
                            f"ДРР {drr:.1f}% за 30 дней превышает порог {drr_max}%",
                        ))
            except Exception:
                pass

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
