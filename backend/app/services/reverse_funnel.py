"""
Reverse-funnel: «задай цель → как её достичь?».

Использует существующий compute_betas + simulate_scenario из WhatIf engine.
Bisection поиск по одной переменной (трафик / цена / бюджет рекламы).

Принципы:
- Если β для нужного рычага НЕ определима (R² мал, мало данных) — честно
  возвращаем сценарий с пометкой 'не_рекомендую' и пояснением.
- Цель достижима только в разумных пределах: max +500% к показам,
  −50% к цене, +500% к рекламе. За пределом — 'недостижимо'.
- Возвращаем actually-achieved value, чтобы было видно если bisection
  не дотянул (например, при потолке β).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.services.whatif_engine import BetasResult, ScenarioInput, ScenarioOutput, simulate_scenario


# Допустимые границы рычага.
LEVER_BOUNDS = {
    "impressions": (-50.0, 500.0),   # %-изменение трафика
    "ad_spend":    (-50.0, 500.0),   # %-изменение рекламного бюджета
    "seller_price": (-50.0, 50.0),   # %-изменение цены продавца
}

BISECTION_MAX_ITER = 25
TOLERANCE_PCT = 0.5  # достижение цели с погрешностью 0.5%


@dataclass
class ReverseScenario:
    lever: str                       # 'impressions' | 'ad_spend' | 'seller_price'
    label: str                       # «Поднять трафик», «Увеличить рекламу», «Снизить цену»
    feasible: bool
    reason: str | None               # объяснение если feasible=False
    lever_value_pct: float | None    # на сколько % нужно подвинуть рычаг
    achieved: ScenarioOutput | None  # какой будет результат


def _build_scenario(lever: str, value_pct: float, betas: BetasResult) -> ScenarioInput:
    inp = ScenarioInput(name="reverse")
    if lever == "impressions":
        inp.impressions_pct = value_pct
    elif lever == "ad_spend":
        inp.ad_spend_pct = value_pct
    elif lever == "seller_price":
        inp.seller_price_pct = value_pct
        # Для цены β обязательна (без неё simulate не двинет спрос).
        # Берём из betas, fallback −1.0 (умеренная отрицательная эластичность).
        if betas.seller_price_to_orders.beta:
            inp.override_beta_price = betas.seller_price_to_orders.beta
        else:
            inp.override_beta_price = -1.0
    return inp


def _metric_value(out: ScenarioOutput, metric: str) -> float:
    return {
        "revenue":     out.revenue,
        "orders":      float(out.orders),
        "delivered":   float(out.delivered),
        "net_profit":  out.net_profit,
        "operating_profit": out.operating_profit,
    }.get(metric, 0.0)


def _lever_feasibility(lever: str, betas: BetasResult) -> tuple[bool, str | None]:
    """Можно ли вообще двинуть этот рычаг — есть ли надёжная β?"""
    if lever == "impressions":
        return True, None  # трафик прокачивается напрямую, без β
    if lever == "ad_spend":
        b = betas.ad_spend_to_imp
        if not b.beta or b.confidence == "low":
            return False, f"β рекламы ненадёжна (R²={b.r2}, {b.confidence}). " \
                          "Прибавка бюджета не предскажет рост трафика на твоих данных."
        return True, None
    if lever == "seller_price":
        b = betas.seller_price_to_orders
        if not b.beta or b.confidence == "low":
            return False, f"β цены ненадёжна (R²={b.r2 if b.r2 else 'нет данных'}, {b.confidence}). " \
                          "Снижение цены не предскажет рост спроса на твоих данных."
        return True, None
    return False, f"неизвестный рычаг: {lever}"


def solve_for_target(
    *,
    lever: str,
    target_metric: str,
    target_value: float,
    base: dict,
    seller_price: float,
    cost: float,
    commission_pct: float,
    tax_regime: str,
    tax_rate: float,
    vat_rate: float | None,
    betas: BetasResult,
    base_net_profit: float,
) -> ReverseScenario:
    """Bisection по одной переменной до достижения target_metric ≈ target_value."""
    label = {
        "impressions":  "Поднять трафик",
        "ad_spend":     "Увеличить рекламу",
        "seller_price": "Снизить цену",
    }[lever]

    feasible, reason = _lever_feasibility(lever, betas)
    if not feasible:
        return ReverseScenario(lever, label, False, reason, None, None)

    lo, hi = LEVER_BOUNDS[lever]
    # Для seller_price (отрицательная эластичность) при цели «больше revenue/orders»
    # bisection ищем СНИЖЕНИЕ цены — но и в обе стороны, пусть bisection сам решит.

    def _eval(pct: float) -> tuple[float, ScenarioOutput]:
        scen = _build_scenario(lever, pct, betas)
        out = simulate_scenario(
            base=base, seller_price=seller_price, cost=cost,
            commission_pct=commission_pct, tax_regime=tax_regime,
            tax_rate=tax_rate, vat_rate=vat_rate, betas=betas,
            scenario=scen, base_net_profit=base_net_profit,
        )
        return _metric_value(out, target_metric), out

    lo_val, lo_out = _eval(lo)
    hi_val, hi_out = _eval(hi)

    # Если ни на каком краю не достижимо — недостижимо
    if not (min(lo_val, hi_val) <= target_value <= max(lo_val, hi_val)):
        # вернём ближайший достижимый край и объяснение
        if abs(lo_val - target_value) < abs(hi_val - target_value):
            best_pct, best_out = lo, lo_out
        else:
            best_pct, best_out = hi, hi_out
        return ReverseScenario(
            lever, label, False,
            f"Целевое значение {target_metric}={target_value:,.0f} недостижимо в "
            f"границах рычага [{lo}…{hi}%]. Максимум что можно: "
            f"{max(lo_val, hi_val):,.0f}.",
            best_pct, best_out,
        )

    # Bisection
    for _ in range(BISECTION_MAX_ITER):
        mid = (lo + hi) / 2
        mid_val, mid_out = _eval(mid)
        if abs(mid_val - target_value) / max(abs(target_value), 1) < TOLERANCE_PCT / 100:
            return ReverseScenario(lever, label, True, None, round(mid, 2), mid_out)
        # Определяем направление: monotonic по lever
        if (mid_val < target_value) == (lo_val < target_value):
            lo, lo_val = mid, mid_val
        else:
            hi, hi_val = mid, mid_val

    final_val, final_out = _eval(mid)
    return ReverseScenario(lever, label, True, None, round(mid, 2), final_out)


def scenario_to_dict(s: ReverseScenario) -> dict:
    return {
        "lever": s.lever,
        "label": s.label,
        "feasible": s.feasible,
        "reason": s.reason,
        "lever_value_pct": s.lever_value_pct,
        "achieved": asdict(s.achieved) if s.achieved else None,
    }
