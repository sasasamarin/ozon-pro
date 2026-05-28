"""
3-осевой ABC-анализ — пункт 3 (nepsell-канон).

Классифицируем товары по трём независимым осям:
- выручка (revenue)
- валовая прибыль (gross_profit = revenue − cogs − commission − logistics)
- чистая прибыль (net_profit = gross − ad_spend − OPEX share)

На каждой оси: A = верхние 80%, B = 80-95%, C = 95-100% (классика Парето).

Сводная классификация:
- AAA → A во всех трёх осях (приоритет №1, защищать и масштабировать)
- AA  → A в двух осях
- A   → A в одной оси
- C   → C во всех трёх (кандидат на вывод из ассортимента)

ВАЖНО: валовая ось работает если заполнена себестоимость (cost_price).
       Чистая работает если ещё и расходы (external_expenses).
       Если данные неполные → ось помечена как "n/a", и сводный класс
       считается только по доступным.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.services.forecasting import ForecastConfidence, ForecastDefaults


@dataclass
class AxisClassification:
    """Классификация по одной оси (выручка / валовая / чистая)."""

    enabled: bool                          # доступна ли ось (есть ли данные)
    rank_by_product: dict[uuid.UUID, str]  # product_id → 'A'/'B'/'C'/'n/a'
    cumulative_share: dict[uuid.UUID, float]  # product_id → накопленная доля


@dataclass
class ABCResult:
    revenue: AxisClassification
    gross: AxisClassification
    net: AxisClassification

    # Сводный класс по 3 осям: 'AAA' / 'AA' / 'A' / 'BBB' / .... / 'CCC'
    overall: dict[uuid.UUID, str]
    confidence: dict[uuid.UUID, str]


def _classify_axis(values: dict[uuid.UUID, float]) -> AxisClassification:
    """Один проход Парето: A/B/C по накопленной доле."""
    if not values or sum(values.values()) <= 0:
        return AxisClassification(
            enabled=False,
            rank_by_product={k: "n/a" for k in values},
            cumulative_share={k: 0.0 for k in values},
        )

    total = sum(values.values())
    sorted_items = sorted(values.items(), key=lambda kv: kv[1], reverse=True)

    ranks: dict[uuid.UUID, str] = {}
    shares: dict[uuid.UUID, float] = {}
    cumulative = 0.0
    for pid, v in sorted_items:
        cumulative += v / total
        shares[pid] = cumulative
        if cumulative <= ForecastDefaults.ABC_A_THRESHOLD:
            ranks[pid] = "A"
        elif cumulative <= ForecastDefaults.ABC_B_THRESHOLD:
            ranks[pid] = "B"
        else:
            ranks[pid] = "C"

    return AxisClassification(enabled=True, rank_by_product=ranks, cumulative_share=shares)


def abc_classify_3axis(
    *,
    revenue_by_product: dict[uuid.UUID, float],
    gross_by_product: dict[uuid.UUID, float] | None = None,
    net_by_product: dict[uuid.UUID, float] | None = None,
) -> ABCResult:
    """Главный вход. Передавай только те оси, по которым есть данные."""
    rev_axis = _classify_axis(revenue_by_product)
    gross_axis = _classify_axis(gross_by_product or {})
    net_axis = _classify_axis(net_by_product or {})

    overall: dict[uuid.UUID, str] = {}
    confidence: dict[uuid.UUID, str] = {}

    all_pids = set(revenue_by_product.keys())
    if gross_by_product:
        all_pids |= set(gross_by_product.keys())
    if net_by_product:
        all_pids |= set(net_by_product.keys())

    for pid in all_pids:
        labels: list[str] = []
        if rev_axis.enabled:
            labels.append(rev_axis.rank_by_product.get(pid, "n/a"))
        if gross_axis.enabled:
            labels.append(gross_axis.rank_by_product.get(pid, "n/a"))
        if net_axis.enabled:
            labels.append(net_axis.rank_by_product.get(pid, "n/a"))

        # Считаем сколько A/B/C в строке. AAA = A везде; C — C везде.
        a_count = sum(1 for x in labels if x == "A")
        c_count = sum(1 for x in labels if x == "C")
        n_axes = sum(1 for x in labels if x != "n/a")

        if n_axes == 3 and a_count == 3:
            overall[pid] = "AAA"
        elif n_axes >= 2 and a_count == n_axes:
            overall[pid] = "AA" if n_axes == 2 else "AAA"
        elif a_count >= 1:
            overall[pid] = "A"
        elif n_axes == 3 and c_count == 3:
            overall[pid] = "CCC"
        elif n_axes >= 2 and c_count == n_axes:
            overall[pid] = "CC"
        elif c_count >= 1 and a_count == 0:
            overall[pid] = "C"
        else:
            overall[pid] = "B"

        # Confidence по полноте осей:
        # high = все 3, medium = 2, low = 1
        if n_axes == 3:
            confidence[pid] = ForecastConfidence.HIGH.value
        elif n_axes == 2:
            confidence[pid] = ForecastConfidence.MEDIUM.value
        else:
            confidence[pid] = ForecastConfidence.LOW.value

    return ABCResult(
        revenue=rev_axis,
        gross=gross_axis,
        net=net_axis,
        overall=overall,
        confidence=confidence,
    )
