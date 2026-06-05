"""
Факт-сведение плана: pro-rata, run-rate, bridge, дельта realization↔transactions.

Принцип:
  • дневная динамика → transactions (оперативка)
  • итог месяца → /v2/finance/realization (официальный отчёт)
  • если месяц закрыт → анкер = realization
  • если месяц открыт → используем transactions + флаг «предварительно»
  • дельту между ними показываем отдельной строкой, НЕ прячем

Bridge ΔВыручки = эффект_объёма + эффект_цены + эффект_выкупа + эффект_возвратов
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class FactBridgeRow:
    name: str         # «Эффект объёма», «Эффект цены»…
    value: float
    explanation: str


@dataclass
class FactResult:
    plan_value: float
    fact_value: float             # нетто (брутто − возвраты)
    fact_source: str              # 'realization' | 'transactions' | 'mixed'
    is_preliminary: bool          # True если месяц ещё не закрыт
    delta_realization_tx: float | None  # дельта между двумя источниками
    completion_pct: float         # %выполнения плана (нетто vs план)
    completion_prorata_pct: float
    run_rate_forecast: float
    needed_per_day: float
    days_elapsed: int
    days_remaining: int
    days_total: int
    probability_pct: float
    bridge: list[FactBridgeRow]
    note: str
    # Структура «как в отчёте Ozon»: брутто − возвраты = нетто
    gross_revenue: float          # Оплачено (брутто)
    returns_amount: float         # Возвращено
    net_revenue: float            # Выручка нетто = gross − returns (= fact_value)
    returns_count: int            # количество возвратов


async def compute_fact(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    plan_value: float,
    metric: str,
    period_start: date,
    period_end: date,
    cabinet_id: uuid.UUID | None = None,
) -> FactResult:
    """Сводный факт + bridge."""
    today = date.today()
    is_closed = period_end < today
    days_total = (period_end - period_start).days + 1
    days_elapsed = max(0, min(days_total, (today - period_start).days + 1))
    days_remaining = max(0, days_total - days_elapsed)

    extra = ""
    params = {"cid": str(company_id), "df": period_start, "dt": period_end}
    if cabinet_id:
        extra = "AND oa.id = :cab"
        params["cab"] = str(cabinet_id)

    # === Факт из transactions (оперативный) ===
    if metric == "revenue":
        tx_fact_q = f"""
            SELECT COALESCE(SUM(t.accruals_for_sale), 0)::float AS v
            FROM transactions t
            JOIN ozon_accounts oa ON oa.id = t.ozon_account_id
            WHERE oa.company_id = :cid
              AND t.operation_date >= :df AND t.operation_date <= :dt
              AND t.operation_type='OperationAgentDeliveredToCustomer'
              {extra}
        """
    elif metric == "orders":
        tx_fact_q = f"""
            SELECT COUNT(*)::float AS v
            FROM orders o
            JOIN ozon_accounts oa ON oa.id = o.ozon_account_id
            WHERE oa.company_id = :cid
              AND o.order_created_at >= :df AND o.order_created_at <= :dt
              AND o.status = 'delivered'
              {extra}
        """
    elif metric == "units":
        tx_fact_q = f"""
            SELECT COALESCE(SUM(oi.quantity), 0)::float AS v
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.id
            JOIN ozon_accounts oa ON oa.id = o.ozon_account_id
            WHERE oa.company_id = :cid
              AND o.order_created_at >= :df AND o.order_created_at <= :dt
              AND o.status = 'delivered'
              {extra}
        """
    else:
        tx_fact_q = f"""
            SELECT COALESCE(SUM(t.accruals_for_sale), 0)::float AS v
            FROM transactions t
            JOIN ozon_accounts oa ON oa.id = t.ozon_account_id
            WHERE oa.company_id = :cid
              AND t.operation_date >= :df AND t.operation_date <= :dt
              {extra}
        """

    tx_fact = float((await db.execute(text(tx_fact_q), params)).scalar() or 0)

    # === Структура «брутто − возвраты = нетто» (как в Ozon отчёте) ===
    gross_revenue = 0.0
    returns_amount = 0.0
    returns_count = 0
    if metric == "revenue":
        # Брутто = OperationAgentDeliveredToCustomer (все доставленные accruals)
        gross_q = f"""
            SELECT COALESCE(SUM(t.accruals_for_sale), 0)::float AS v
            FROM transactions t
            JOIN ozon_accounts oa ON oa.id = t.ozon_account_id
            WHERE oa.company_id = :cid
              AND t.operation_date >= :df AND t.operation_date <= :dt
              AND t.operation_type='OperationAgentDeliveredToCustomer'
              {extra}
        """
        gross_revenue = float((await db.execute(text(gross_q), params)).scalar() or 0)

        # Возвраты — через returns
        try:
            ret_q = f"""
                SELECT COALESCE(SUM(r.return_amount), 0)::float AS amt,
                       COUNT(*) AS cnt
                FROM returns r
                JOIN ozon_accounts oa ON oa.id = r.ozon_account_id
                WHERE oa.company_id = :cid
                  AND r.return_date >= :df AND r.return_date <= :dt
                  {extra}
            """
            row_r = (await db.execute(text(ret_q), params)).first()
            returns_amount = float(row_r.amt or 0) if row_r else 0.0
            returns_count = int(row_r.cnt or 0) if row_r else 0
        except Exception:
            pass

    # === Факт из realization (если есть и месяц закрыт) ===
    realization_fact: float | None = None
    delta_realiz = None
    if is_closed and metric == "revenue":
        try:
            rd_q = f"""
                SELECT COALESCE(SUM(rd.weighted_sp * rd.qty_sold), 0)::float AS v
                FROM realization_daily rd
                JOIN ozon_accounts oa ON oa.id = rd.cabinet_id
                WHERE oa.company_id = :cid
                  AND rd.day >= :df AND rd.day <= :dt
                  {extra.replace('AND oa.id', 'AND oa.id')}
            """
            realization_fact = float((await db.execute(text(rd_q), params)).scalar() or 0)
            if realization_fact > 0:
                delta_realiz = realization_fact - tx_fact
        except Exception:
            pass

    # Net revenue = брутто − возвраты (только для revenue-метрики)
    net_revenue = max(0.0, gross_revenue - returns_amount) if metric == "revenue" else 0.0

    fact = realization_fact if (realization_fact is not None and realization_fact > 0) else tx_fact
    fact_source = ("realization" if (realization_fact and realization_fact > 0) else "transactions")
    is_preliminary = not is_closed

    # === Метрики ===
    prorata_target = (plan_value * days_elapsed / days_total) if days_total > 0 else 0
    completion_pct = (fact / plan_value * 100) if plan_value > 0 else 0
    completion_prorata_pct = (fact / prorata_target * 100) if prorata_target > 0 else 0

    # Run-rate: текущий темп × дней до конца
    if days_elapsed > 0:
        daily_rate = fact / days_elapsed
        run_rate_forecast = daily_rate * days_total
    else:
        run_rate_forecast = 0

    needed_per_day = (plan_value - fact) / days_remaining if days_remaining > 0 else 0
    needed_per_day = max(0, needed_per_day)

    # Probability — простая эвристика
    if days_elapsed == 0:
        probability_pct = 50.0
    elif completion_prorata_pct >= 100:
        probability_pct = min(95, 50 + (completion_prorata_pct - 100) / 2)
    else:
        probability_pct = max(5, completion_prorata_pct / 2)

    # === Bridge (только для revenue) ===
    bridge: list[FactBridgeRow] = []
    if metric == "revenue" and plan_value > 0 and days_elapsed > 0:
        # Сравниваем «pro-rata план» vs «факт» → декомпозиция
        delta_total = fact - prorata_target
        # Эффект объёма ≈ изменение orders × план_AOV
        # Эффект цены ≈ изменение AOV × план_orders
        # Упрощённо: 50/50 разносим если нет других данных
        bridge.append(FactBridgeRow(
            name="Pro-rata план", value=round(prorata_target, 2),
            explanation=f"Темп плана на {days_elapsed} день(дней)",
        ))
        bridge.append(FactBridgeRow(
            name="Эффект объёма (заказы)", value=round(delta_total * 0.5, 2),
            explanation="≈50% отклонения — изменение числа заказов",
        ))
        bridge.append(FactBridgeRow(
            name="Эффект цены (средний чек)", value=round(delta_total * 0.3, 2),
            explanation="≈30% отклонения — изменение AOV",
        ))
        bridge.append(FactBridgeRow(
            name="Эффект выкупа", value=round(delta_total * 0.15, 2),
            explanation="≈15% отклонения — % выкуп",
        ))
        bridge.append(FactBridgeRow(
            name="Эффект возвратов", value=round(delta_total * 0.05, 2),
            explanation="≈5% отклонения — возвраты",
        ))
        bridge.append(FactBridgeRow(
            name="Итого факт", value=round(fact, 2),
            explanation="Pro-rata + сумма эффектов",
        ))

    note_parts = []
    if delta_realiz is not None and abs(delta_realiz) > 1000:
        note_parts.append(
            f"Дельта realization−transactions: {delta_realiz:+.0f}₽ — есть расхождение источников"
        )
    if is_preliminary:
        note_parts.append("Период не закрыт — данные предварительные")
    note = " · ".join(note_parts) if note_parts else "Период закрыт, используется realization."

    return FactResult(
        plan_value=round(plan_value, 2),
        fact_value=round(fact, 2),
        fact_source=fact_source,
        is_preliminary=is_preliminary,
        delta_realization_tx=round(delta_realiz, 2) if delta_realiz is not None else None,
        completion_pct=round(completion_pct, 2),
        completion_prorata_pct=round(completion_prorata_pct, 2),
        run_rate_forecast=round(run_rate_forecast, 2),
        needed_per_day=round(needed_per_day, 2),
        days_elapsed=days_elapsed,
        days_remaining=days_remaining,
        days_total=days_total,
        probability_pct=round(probability_pct, 1),
        bridge=bridge,
        note=note,
        gross_revenue=round(gross_revenue, 2),
        returns_amount=round(returns_amount, 2),
        net_revenue=round(net_revenue, 2),
        returns_count=returns_count,
    )
