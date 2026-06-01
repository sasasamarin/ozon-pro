"""
Расчёт графика платежей по займу.

Поддерживаются:
- annuity        — аннуитет (равные платежи, последний может округляться)
- differentiated — дифференцированный (тело равными частями, % уменьшается)

Тело и процент возвращаются отдельно — это критично:
тело в P&L не идёт, только в ДДС; процент идёт и в ДДС, и в P&L.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class ScheduleEntry:
    seq: int
    pay_date: date
    principal_part: Decimal
    interest_part: Decimal


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    # клампим день на конец месяца если переполнение (например 31 → 28/30)
    for day in (d.day, 28, 27, 26):
        try:
            return d.replace(year=year, month=month, day=day)
        except ValueError:
            continue
    raise ValueError(f"Не удалось добавить {months} мес к {d}")


def build_schedule(
    *,
    principal: Decimal,
    rate_pct_annual: Decimal,
    term_months: int,
    issued_at: date,
    schedule_type: str = "annuity",
) -> list[ScheduleEntry]:
    """
    Возвращает список из term_months платежей.
    Первый платёж — через 1 месяц после выдачи.

    schedule_type:
      annuity        — формула P×i / (1−(1+i)^−n), последний месяц корректируется
      differentiated — тело = P/n, процент = остаток × i

    rate_pct_annual = 0 → процент = 0, оба типа сводятся к равному делению тела.
    """
    if term_months <= 0:
        return []
    if principal <= 0:
        return []

    monthly_rate = (rate_pct_annual or Decimal("0")) / Decimal("100") / Decimal("12")

    entries: list[ScheduleEntry] = []
    remaining = principal

    if schedule_type == "differentiated" or monthly_rate == 0:
        base_principal_part = _round2(principal / Decimal(term_months))
        for i in range(1, term_months + 1):
            interest = _round2(remaining * monthly_rate) if monthly_rate > 0 else Decimal("0")
            principal_part = base_principal_part if i < term_months else _round2(remaining)
            entries.append(ScheduleEntry(
                seq=i,
                pay_date=_add_months(issued_at, i),
                principal_part=principal_part,
                interest_part=interest,
            ))
            remaining -= principal_part
        return entries

    # Annuity: PMT = P × i / (1 − (1+i)^−n)
    one_plus_i_pow_neg_n = (Decimal("1") + monthly_rate) ** (-term_months)
    annuity_payment = _round2(
        principal * monthly_rate / (Decimal("1") - one_plus_i_pow_neg_n)
    )
    for i in range(1, term_months + 1):
        interest = _round2(remaining * monthly_rate)
        if i < term_months:
            principal_part = _round2(annuity_payment - interest)
        else:
            # последний платёж = остаток, чтобы compensate округления
            principal_part = _round2(remaining)
        entries.append(ScheduleEntry(
            seq=i,
            pay_date=_add_months(issued_at, i),
            principal_part=principal_part,
            interest_part=interest,
        ))
        remaining -= principal_part

    return entries
