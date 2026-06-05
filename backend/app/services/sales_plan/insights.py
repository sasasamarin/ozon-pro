"""
Авто-инсайты Plan-Fact: «зашёл и за 5 сек понял что идёт».

Генерирует текстовый вердикт:
  • Главный результат: отстаёте/опережаете, цифра, %
  • Доминирующий фактор (из bridge): что главное двигает отклонение
  • Top SKU-killers / heroes: 3 SKU с максимальным отрицательным/
    положительным вкладом в отставание
  • Реалистичность плана: цель vs исторический max
  • Конкретное действие: «нужен темп X/день», «дефицит склада Y шт»

Все числа берутся из готовых рассчётов (compute_fact, sku_rows),
никаких дополнительных запросов к БД.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Insight:
    level: str          # 'critical' | 'warning' | 'info' | 'success'
    title: str
    detail: str
    action: str | None = None


def build_insights(
    *,
    plan_value: float,
    fact_value: float,
    completion_prorata_pct: float,
    run_rate_forecast: float,
    needed_per_day: float,
    days_remaining: int,
    probability_pct: float,
    bridge: list[dict],
    sku_rows: list[dict] | None = None,
    stock_hints: list[dict] | None = None,
    metric_code: str = "revenue",
) -> list[Insight]:
    """Возвращает упорядоченный список инсайтов (важное наверху)."""
    insights: list[Insight] = []
    unit = "₽" if metric_code in ("revenue", "gross_profit", "net_profit") else "шт"

    delta = fact_value - plan_value
    delta_prorata = completion_prorata_pct - 100  # п.п.

    # === 1. Главный вердикт ===
    if completion_prorata_pct >= 110:
        insights.append(Insight(
            level="success",
            title=f"🚀 Опережаете план на {completion_prorata_pct - 100:.0f}%",
            detail=(
                f"При текущем темпе выйдете на ~{run_rate_forecast:,.0f} {unit}, "
                f"при плане {plan_value:,.0f} {unit}. Вероятность {probability_pct:.0f}%."
            ),
            action="Можно увеличить план или направить ресурсы на другие SKU.",
        ))
    elif completion_prorata_pct >= 95:
        insights.append(Insight(
            level="success",
            title=f"🎯 В цель — {completion_prorata_pct:.0f}% от темпа",
            detail=(
                f"Текущий темп даёт прогноз ~{run_rate_forecast:,.0f} {unit}. "
                f"Вероятность достичь плана {probability_pct:.0f}%."
            ),
        ))
    elif completion_prorata_pct >= 70:
        insights.append(Insight(
            level="warning",
            title=f"⚠ Отстаёте: {completion_prorata_pct:.0f}% от темпа",
            detail=(
                f"При текущей скорости выйдете на ~{run_rate_forecast:,.0f} {unit}. "
                f"До плана нужно {needed_per_day:,.0f} {unit}/день "
                f"({days_remaining} дней)."
            ),
            action=(
                f"Чтобы дотянуть до плана, нужно увеличить темп до "
                f"{needed_per_day:,.0f} {unit}/день."
            ),
        ))
    else:
        insights.append(Insight(
            level="critical",
            title=f"🔴 Сильно отстаёте: {completion_prorata_pct:.0f}% от темпа",
            detail=(
                f"При текущем темпе план будет выполнен на "
                f"~{(run_rate_forecast / plan_value * 100 if plan_value else 0):.0f}%. "
                f"Вероятность достичь {probability_pct:.0f}%."
            ),
            action=(
                f"Нужен темп {needed_per_day:,.0f} {unit}/день. "
                f"Если столько не сделать — пересмотри план."
            ),
        ))

    # === 2. Доминирующий фактор из bridge ===
    if bridge:
        # Берём bridge без последнего «Итого» (если есть)
        eff = [b for b in bridge if "итого" not in b.get("name", "").lower() and "pro-rata" not in b.get("name", "").lower()]
        if eff:
            # Сортируем по |value|
            sorted_eff = sorted(eff, key=lambda b: abs(b.get("value", 0)), reverse=True)
            top = sorted_eff[0]
            sign = "+" if top.get("value", 0) >= 0 else ""
            insights.append(Insight(
                level="info",
                title=f"📊 Главный фактор: {top['name']}",
                detail=(
                    f"{sign}{top['value']:,.0f} {unit} — "
                    f"{top.get('explanation', 'основной вклад в отклонение')}."
                ),
            ))

    # === 3. SKU-киллеры / герои ===
    if sku_rows:
        killers = [r for r in sku_rows if (r.get("deviation") or 0) < 0]
        heroes = [r for r in sku_rows if (r.get("deviation") or 0) > 0]

        if killers and completion_prorata_pct < 95:
            killers_sorted = sorted(killers, key=lambda r: r.get("deviation", 0))[:3]
            killer_lines = []
            for k in killers_sorted:
                killer_lines.append(
                    f"  • {k.get('sku', '—')}: −{abs(k.get('deviation', 0)):,.0f} {unit}"
                )
            insights.append(Insight(
                level="warning",
                title=f"🪦 Тянут вниз ({len(killers)} SKU)",
                detail="Топ-3 по отставанию:\n" + "\n".join(killer_lines),
                action="Глянь карточки SKU — что с ценой/остатком/рекламой?",
            ))

        if heroes and completion_prorata_pct >= 95:
            heroes_sorted = sorted(heroes, key=lambda r: -(r.get("deviation", 0)))[:3]
            hero_lines = []
            for h in heroes_sorted:
                hero_lines.append(
                    f"  • {h.get('sku', '—')}: +{h.get('deviation', 0):,.0f} {unit}"
                )
            insights.append(Insight(
                level="success",
                title=f"🏆 Тянут вверх ({len(heroes)} SKU)",
                detail="Топ-3 героев:\n" + "\n".join(hero_lines),
                action="Усилить рекламу / поднять цену на них.",
            ))

    # === 4. Реалистичность плана ===
    if sku_rows and plan_value > 0:
        forecast_total = sum(r.get("forecast", 0) for r in sku_rows)
        if forecast_total > 0 and forecast_total < plan_value * 0.7:
            gap_pct = (1 - forecast_total / plan_value) * 100
            insights.append(Insight(
                level="warning",
                title=f"🎲 План оптимистичен на {gap_pct:.0f}%",
                detail=(
                    f"Run-rate прогноз {forecast_total:,.0f} {unit} меньше плана "
                    f"{plan_value:,.0f} {unit} на {gap_pct:.0f}%. "
                    f"Возможно цель завышена для текущего темпа."
                ),
                action="Пересмотри ожидания или подними скорость (реклама / цены).",
            ))

    # === 5. Дефицит склада ===
    if stock_hints:
        deficit_count = len(stock_hints)
        total_deficit = sum(h.get("deficit_units", 0) for h in stock_hints)
        if deficit_count > 0:
            insights.append(Insight(
                level="warning",
                title=f"📦 Дефицит склада: {deficit_count} SKU, ~{total_deficit:,.0f} шт",
                detail=(
                    f"Под план не хватает товара. Если не подкинуть поставку — "
                    f"эти SKU не закроют план."
                ),
                action="Создать потребность в поставке (см. карточку выше).",
            ))

    return insights
