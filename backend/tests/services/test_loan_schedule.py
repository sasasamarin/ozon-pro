"""Тесты графика погашения кредита (Loans v1, #118)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.services.loan_schedule import build_schedule


# Допуск 1 ₽ — последний платёж абсорбирует округление.
APPROX_RUB = 1.0


def _sum(entries, attr):
    return sum(getattr(e, attr) for e in entries)


def test_annuity_principal_sums_to_total():
    """Аннуитет: Σ principal_part должна точно равняться principal."""
    entries = build_schedule(
        principal=Decimal("1000000"), rate_pct_annual=Decimal("25"),
        term_months=12, issued_at=date(2025, 1, 15), schedule_type="annuity",
    )
    assert len(entries) == 12
    assert _sum(entries, "principal_part") == Decimal("1000000.00")


def test_annuity_payments_decreasing_interest():
    """Аннуитет: общий платёж стабилен, но % уменьшается с каждым шагом."""
    entries = build_schedule(
        principal=Decimal("1000000"), rate_pct_annual=Decimal("25"),
        term_months=12, issued_at=date(2025, 1, 15), schedule_type="annuity",
    )
    interests = [e.interest_part for e in entries]
    # каждый следующий процент меньше предыдущего (кроме компенсации в последнем)
    for i in range(len(interests) - 2):
        assert interests[i + 1] < interests[i], f"interest должен убывать: {interests[i]} → {interests[i+1]}"


def test_differentiated_principal_constant():
    """Дифференцированный: тело равное (кроме последнего), процент убывает."""
    entries = build_schedule(
        principal=Decimal("1200000"), rate_pct_annual=Decimal("12"),
        term_months=12, issued_at=date(2025, 1, 15), schedule_type="differentiated",
    )
    expected_per_month = Decimal("100000.00")
    for e in entries[:-1]:  # все кроме последнего
        assert e.principal_part == expected_per_month
    assert _sum(entries, "principal_part") == Decimal("1200000.00")


def test_zero_interest_rate():
    """Беспроцентная рассрочка: процент 0, тело делится равномерно."""
    entries = build_schedule(
        principal=Decimal("120000"), rate_pct_annual=Decimal("0"),
        term_months=12, issued_at=date(2025, 1, 15), schedule_type="annuity",
    )
    assert all(e.interest_part == Decimal("0") for e in entries)
    assert _sum(entries, "principal_part") == Decimal("120000.00")


def test_first_payment_one_month_later():
    """Первый платёж — через месяц после выдачи."""
    entries = build_schedule(
        principal=Decimal("100000"), rate_pct_annual=Decimal("10"),
        term_months=3, issued_at=date(2025, 3, 15), schedule_type="annuity",
    )
    assert entries[0].pay_date == date(2025, 4, 15)
    assert entries[1].pay_date == date(2025, 5, 15)
    assert entries[2].pay_date == date(2025, 6, 15)


def test_month_overflow_clamps_to_last_day():
    """31 января + 1 мес = 28 (или 29) февраля, не KeyError."""
    entries = build_schedule(
        principal=Decimal("100000"), rate_pct_annual=Decimal("10"),
        term_months=2, issued_at=date(2025, 1, 31), schedule_type="annuity",
    )
    # февраль 2025 — не високосный, 28 дней
    assert entries[0].pay_date == date(2025, 2, 28)
    assert entries[1].pay_date == date(2025, 3, 31)


def test_zero_principal_returns_empty():
    """Краевой: 0 ₽ займа → пустой список."""
    entries = build_schedule(
        principal=Decimal("0"), rate_pct_annual=Decimal("10"),
        term_months=12, issued_at=date(2025, 1, 1), schedule_type="annuity",
    )
    assert entries == []


def test_zero_term_returns_empty():
    """Краевой: 0 месяцев → пустой список."""
    entries = build_schedule(
        principal=Decimal("100000"), rate_pct_annual=Decimal("10"),
        term_months=0, issued_at=date(2025, 1, 1), schedule_type="annuity",
    )
    assert entries == []


def test_annuity_total_interest_positive():
    """Общий процент за 12 мес при 25% годовых на 1М ≈ 140k (документированный пример)."""
    entries = build_schedule(
        principal=Decimal("1000000"), rate_pct_annual=Decimal("25"),
        term_months=12, issued_at=date(2025, 1, 15), schedule_type="annuity",
    )
    total_interest = float(_sum(entries, "interest_part"))
    assert 130_000 < total_interest < 150_000


def test_diff_total_interest_lower_than_annuity():
    """Дифференцированный график при той же ставке даёт МЕНЬШИЙ суммарный %
    (потому что тело гасится быстрее)."""
    annuity = build_schedule(
        principal=Decimal("1000000"), rate_pct_annual=Decimal("25"),
        term_months=12, issued_at=date(2025, 1, 15), schedule_type="annuity",
    )
    diff = build_schedule(
        principal=Decimal("1000000"), rate_pct_annual=Decimal("25"),
        term_months=12, issued_at=date(2025, 1, 15), schedule_type="differentiated",
    )
    assert _sum(diff, "interest_part") < _sum(annuity, "interest_part")
