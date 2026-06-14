"""
Ядро RBAC-изоляции кабинетов — чистая (без БД) функция пересечения.

Вынесено из api/deps_cabinets.filter_requested_cabinet_ids, чтобы инвариант
«участник никогда не видит чужой кабинет, даже если явно его запросил» можно
было покрыть тестом без БД (tests/services/test_cabinet_access.py).
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable


def intersect_cabinets(
    requested: Iterable[uuid.UUID] | None,
    visible: Iterable[uuid.UUID],
) -> list[uuid.UUID]:
    """Пересечь запрошенные кабинеты с видимыми (доступными пользователю).

    - requested пуст/None → возвращаем ВСЕ видимые;
    - иначе → только те запрошенные, что есть среди видимых. Запрос чужого
      кабинета молча отбрасывается (изоляция данных), порядок сохраняется.
    """
    visible_list = list(visible)
    if not requested:
        return visible_list
    visible_set = set(visible_list)
    return [c for c in requested if c in visible_set]
