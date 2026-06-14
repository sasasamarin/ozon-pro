"""
Тесты RBAC-изоляции кабинетов (services/cabinet_access.intersect_cabinets).

Главный инвариант: участник НИКОГДА не видит чужой кабинет, даже если явно
передал его id в cabinet_ids. Защита от утечки данных между компаниями/членами.
"""
from __future__ import annotations

import uuid

from app.services.cabinet_access import intersect_cabinets

A = uuid.UUID(int=1)
B = uuid.UUID(int=2)
C = uuid.UUID(int=3)   # чужой кабинет — НЕ в visible
D = uuid.UUID(int=4)


def test_none_requested_returns_all_visible():
    assert intersect_cabinets(None, [A, B]) == [A, B]


def test_empty_requested_returns_all_visible():
    assert intersect_cabinets([], [A, B]) == [A, B]


def test_requested_subset_returns_subset():
    assert intersect_cabinets([A], [A, B]) == [A]


def test_foreign_cabinet_is_dropped():
    """Запрос чужого кабинета (C) молча отбрасывается — ядро изоляции."""
    assert intersect_cabinets([A, C], [A, B]) == [A]
    assert C not in intersect_cabinets([C], [A, B])


def test_only_foreign_requested_returns_empty():
    """Если запросили ТОЛЬКО чужие — не видно ничего (не утекает в «все»)."""
    assert intersect_cabinets([C, D], [A, B]) == []


def test_empty_visible_never_leaks():
    """Нет доступных кабинетов → ничего не видно при любом запросе."""
    assert intersect_cabinets([A, B], []) == []
    assert intersect_cabinets(None, []) == []


def test_order_preserved():
    assert intersect_cabinets([B, A], [A, B]) == [B, A]
