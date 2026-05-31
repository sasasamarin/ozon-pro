"""
Единые константы и helper'ы финансовых расчётов.

До этого LOGISTICS_PER_UNIT, ACQUIRING_PCT, DEFAULT_COMMISSION_PCT дублировались
в analytics_engine, whatif_engine, product_economics — с расхождениями (в
reconcile_realization было даже 41% fallback вместо 25%). Эквайринг в нескольких
местах считался от revenue, что некорректно — реально он считается от
customer_price (а на бэке для аппроксимации — от seller_price).

Все формулы P&L/Economics/WhatIf должны ходить через эти helper'ы, чтобы:
1. Одна правка → одна точка изменения
2. Помеченные «оценка» vs «факт» — для прозрачности юзеру
3. Готовы к будущему: реальная логистика из Transaction, реальный эквайринг из API
"""
from __future__ import annotations

from dataclasses import dataclass


# === Дефолты (используются как fallback когда реальные данные недоступны) ===

LOGISTICS_PER_UNIT_DEFAULT = 306.0   # средний deliver_to_customer+last_mile (Жираф)
ACQUIRING_PCT_DEFAULT = 1.5          # эквайринг % от продажной цены
DEFAULT_COMMISSION_PCT = 25.0        # если у товара нет sales_percent_fbo


# === Helper'ы с явной пометкой источника ===

@dataclass
class AcquiringCalc:
    amount: float
    source: str  # "api" (из Product.acquiring_amount × qty) / "estimate" (% от seller_price)


def calc_acquiring(
    *, seller_price: float, qty: float,
    product_acquiring_amount: float | None = None,
    pct: float = ACQUIRING_PCT_DEFAULT,
) -> AcquiringCalc:
    """
    Эквайринг = комиссия за эквайринг банка-эквайера за платёж покупателя.

    База: seller_price (НЕ revenue общая, НЕ customer_price).
    Если у Product.acquiring_amount есть значение из Ozon API — используем его × qty.
    Иначе — оценка через pct (default 1.5%) от seller_price × qty.

    Раньше в whatif_engine было `acquiring = revenue * 0.015` — это
    концептуально неверно: revenue включает всю комиссию (включая %-эквайринг
    Ozon), а реальный эквайринг считается от чистой цены продажи.
    Для делящихся товаров результат одинаков, но при росте qty с фикс-ценой
    revenue и seller_price расходятся и формулы дают разные числа.
    """
    if product_acquiring_amount is not None and product_acquiring_amount > 0:
        return AcquiringCalc(amount=product_acquiring_amount * qty, source="api")
    return AcquiringCalc(amount=seller_price * qty * pct / 100, source="estimate")


@dataclass
class LogisticsCalc:
    amount: float
    source: str  # "real" (сумма из Transaction) / "estimate" (qty × default)


def calc_logistics(
    *, qty: float, real_amount: float | None = None,
    per_unit: float = LOGISTICS_PER_UNIT_DEFAULT,
) -> LogisticsCalc:
    """
    Логистика = delivery_to_customer + last_mile + return_logistics за период.

    Если есть реальная сумма из Transaction (сложенная вызывающим из таблицы
    transactions) — используем её как факт. Иначе — оценка qty × 306 ₽.

    Сейчас real_amount передают только из pnl.py (там есть прямая агрегация
    Transaction). analytics_engine, whatif_engine, product_economics используют
    оценку. После ШАГ 3 это станет видно юзеру через source.
    """
    if real_amount is not None:
        return LogisticsCalc(amount=real_amount, source="real")
    return LogisticsCalc(amount=qty * per_unit, source="estimate")


def get_commission_pct(*, product_sales_percent_fbo: float | None) -> float:
    """Возвращает комиссию % для товара. Fallback 25% (среднее по home).

    ВАЖНО: 41% в reconcile_realization было ошибкой — это значение из старого
    кабинета Жирафа, неприменимо как глобальный default.
    """
    if product_sales_percent_fbo is not None and product_sales_percent_fbo > 0:
        return float(product_sales_percent_fbo)
    return DEFAULT_COMMISSION_PCT


# === Удобные алиасы для импорта (legacy совместимость) ===

# Эти алиасы оставлены для тех мест, где замена на helper необязательна
# (например, для отображения в UI как «эвристика 306 ₽»). Не использовать в формулах.
LOGISTICS_PER_UNIT = LOGISTICS_PER_UNIT_DEFAULT
ACQUIRING_PCT = ACQUIRING_PCT_DEFAULT
