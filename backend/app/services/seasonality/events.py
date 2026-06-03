"""
Календарь сезонных событий РФ + Ozon. Константы Python, без миграции.
Юзер: «events в коде». Меняем редко, версионируем через git.

Используется:
- маркеры на YoY-графике (вертикальные линии)
- объяснение пиков в автодетекте
- /seasonality/events endpoint
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls
from enum import Enum
from typing import Literal


class EventKind(str, Enum):
    HOLIDAY = "holiday"   # выходной
    SALE = "sale"         # распродажа
    SEASON = "season"     # сезон (школа, лето)


@dataclass
class SeasonalEvent:
    id: str
    name: str
    kind: EventKind
    # month-day, формат "MM-DD". Для recurring_yearly. Год подставляется.
    month_day_start: str
    month_day_end: str | None = None  # None = однодневное событие
    note: str = ""
    icon: str = ""  # opaque emoji для UI

    def occurs_in_year(self, year: int) -> tuple[date_cls, date_cls]:
        m, d = map(int, self.month_day_start.split("-"))
        start = date_cls(year, m, d)
        if self.month_day_end:
            m2, d2 = map(int, self.month_day_end.split("-"))
            end_year = year if (m2, d2) >= (m, d) else year + 1
            end = date_cls(end_year, m2, d2)
        else:
            end = start
        return start, end


# === РФ + Ozon: основные события года =====================================

EVENTS: list[SeasonalEvent] = [
    # Праздники / гендерные
    SeasonalEvent("ny", "Новогодние праздники", EventKind.HOLIDAY,
                  "12-25", "01-10",
                  "Декабрьский пик подарков + январский спад", "🎄"),
    SeasonalEvent("v14", "День святого Валентина", EventKind.HOLIDAY,
                  "02-14", None,
                  "Подарочные товары, цветы, аксессуары", "💝"),
    SeasonalEvent("v23", "23 февраля", EventKind.HOLIDAY,
                  "02-23", None,
                  "Мужские подарки, инструменты", "🎖️"),
    SeasonalEvent("v8", "8 марта", EventKind.HOLIDAY,
                  "03-08", None,
                  "Женские подарки, цветы, косметика", "🌷"),

    # Сезоны
    SeasonalEvent("school", "К школе", EventKind.SEASON,
                  "08-01", "09-01",
                  "Школьные товары, рюкзаки, канцелярия", "🎒"),
    SeasonalEvent("summer", "Летний сезон", EventKind.SEASON,
                  "05-15", "08-31",
                  "Сад/огород, активный отдых, кондиционеры", "☀️"),
    SeasonalEvent("winter", "Зимний сезон", EventKind.SEASON,
                  "11-01", "02-28",
                  "Отопление, тёплая одежда, обувь", "❄️"),

    # Ozon-специфичные распродажи
    SeasonalEvent("ozon_1111", "11.11 Big Sale", EventKind.SALE,
                  "11-11", None,
                  "Главная распродажа года на Ozon", "💸"),
    SeasonalEvent("black_friday", "Чёрная пятница", EventKind.SALE,
                  "11-24", "11-30",
                  "Глобальная распродажа, последняя пятница ноября", "🛍️"),
    SeasonalEvent("ozon_1212", "12.12 Sale", EventKind.SALE,
                  "12-12", None,
                  "Предновогодняя распродажа Ozon", "🎁"),
    SeasonalEvent("ozon_july", "Летняя распродажа Ozon", EventKind.SALE,
                  "07-07", "07-15",
                  "Летние акции маркетплейса", "🌞"),
]


def events_for_year(year: int) -> list[dict]:
    """Развёрнутый календарь на конкретный год (для оверлеев YoY)."""
    out = []
    for e in EVENTS:
        start, end = e.occurs_in_year(year)
        out.append({
            "id": e.id, "name": e.name, "kind": e.kind.value,
            "date_start": start.isoformat(),
            "date_end": end.isoformat() if end != start else None,
            "note": e.note, "icon": e.icon,
        })
    return out


def events_in_range(date_from: date_cls, date_to: date_cls) -> list[dict]:
    """События попадающие в диапазон (включая повторы по годам)."""
    out: list[dict] = []
    for year in range(date_from.year, date_to.year + 2):
        for e in EVENTS:
            start, end = e.occurs_in_year(year)
            if end < date_from or start > date_to:
                continue
            out.append({
                "id": f"{e.id}-{year}", "name": e.name, "kind": e.kind.value,
                "date_start": start.isoformat(),
                "date_end": end.isoformat() if end != start else None,
                "note": e.note, "icon": e.icon,
                "year": year,
            })
    return out
