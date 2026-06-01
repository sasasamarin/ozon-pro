"""Тесты агрегатора /v2/finance/realization — критично для customer_price бэкфилла."""
from __future__ import annotations

import pytest
from app.services.parsers.ozon_realization_aggregator import (
    aggregate_realization_rows,
    SkuAggregate,
)


def _row(sku: int, cp: float, qty: int, sp: float = 0,
         bonus: float = 0, fee: float = 0,
         offer_id: str | None = None) -> dict:
    """Помогалка: сделать payload-row как у Ozon."""
    return {
        "item": {"sku": sku, "offer_id": offer_id, "name": f"prod-{sku}"},
        "seller_price_per_instance": sp,
        "delivery_commission": {
            "price_per_instance": cp,
            "quantity": qty,
            "bonus": bonus,
            "standard_fee": fee,
        },
        "return_commission": None,
    }


def test_single_row_one_sku():
    """Один товар, одна транзакция."""
    rows = [_row(123, cp=1500.0, qty=2, sp=2500.0, bonus=2000.0, fee=400.0)]
    result = aggregate_realization_rows(rows)
    assert len(result) == 1
    agg = result[123]
    assert agg.qty_sold == 2
    assert agg.weighted_cp == 1500.0
    assert agg.weighted_sp == 2500.0
    assert agg.sum_bonus == 2000.0
    assert agg.sum_fee == 400.0
    assert agg.rows == 1


def test_many_rows_same_sku_weighted_avg():
    """РЕАЛЬНЫЙ кейс: kofemolka в марте — 192 строки на один SKU.
    Каждая строка с разным customer_price → weighted_avg по qty."""
    rows = [
        _row(100, cp=1000.0, qty=10),  # 10 единиц по 1000 = 10000
        _row(100, cp=2000.0, qty=5),   # 5 единиц по 2000 = 10000
        _row(100, cp=1500.0, qty=15),  # 15 единиц по 1500 = 22500
    ]
    result = aggregate_realization_rows(rows)
    agg = result[100]
    assert agg.qty_sold == 30
    # weighted_cp = (10000+10000+22500) / 30 = 42500/30 ≈ 1416.67
    assert agg.weighted_cp == pytest.approx(1416.67, rel=0.001)
    assert agg.rows == 3


def test_multiple_skus_isolated():
    """Разные SKU не смешиваются."""
    rows = [
        _row(100, cp=1000.0, qty=5),
        _row(200, cp=5000.0, qty=2),
        _row(100, cp=2000.0, qty=5),
    ]
    result = aggregate_realization_rows(rows)
    assert len(result) == 2
    assert result[100].weighted_cp == pytest.approx(1500.0)  # (1000*5+2000*5)/10
    assert result[200].weighted_cp == pytest.approx(5000.0)
    assert result[100].qty_sold == 10
    assert result[200].qty_sold == 2


def test_skip_row_without_sku():
    """row без item.sku пропускается, не валит весь батч."""
    rows = [
        _row(100, cp=1000.0, qty=5),
        {"item": {}, "delivery_commission": {"price_per_instance": 999, "quantity": 1}},  # без sku
        _row(100, cp=2000.0, qty=5),
    ]
    result = aggregate_realization_rows(rows)
    assert len(result) == 1
    assert result[100].qty_sold == 10


def test_zero_qty_does_not_break():
    """qty=0 НЕ деление на ноль, weighted_cp=None для агрегата с qty=0."""
    rows = [
        {
            "item": {"sku": 100},
            "seller_price_per_instance": 1000,
            "delivery_commission": {
                "price_per_instance": 500, "quantity": 0, "bonus": 0, "standard_fee": 0,
            },
            "return_commission": None,
        }
    ]
    result = aggregate_realization_rows(rows)
    assert result[100].qty_sold == 0
    assert result[100].weighted_cp is None


def test_return_commission_aggregated():
    """return_commission.quantity и amount складываются."""
    rows = [
        {
            "item": {"sku": 100},
            "seller_price_per_instance": 1000,
            "delivery_commission": {"price_per_instance": 800, "quantity": 5,
                                    "bonus": 0, "standard_fee": 0},
            "return_commission": {"quantity": 1, "amount": 800.0},
        },
        {
            "item": {"sku": 100},
            "seller_price_per_instance": 1000,
            "delivery_commission": {"price_per_instance": 800, "quantity": 3,
                                    "bonus": 0, "standard_fee": 0},
            "return_commission": {"quantity": 2, "amount": 1600.0},
        },
    ]
    result = aggregate_realization_rows(rows)
    assert result[100].qty_returned == 3
    assert result[100].sum_amount_returned == pytest.approx(2400.0)


def test_string_sku_converted_to_int():
    """Ozon API иногда отдаёт sku как строку — int() конвертирует."""
    rows = [
        {
            "item": {"sku": "1234567"},
            "seller_price_per_instance": 1000,
            "delivery_commission": {"price_per_instance": 800, "quantity": 1,
                                    "bonus": 0, "standard_fee": 0},
        }
    ]
    result = aggregate_realization_rows(rows)
    assert 1234567 in result
    assert result[1234567].sku == 1234567


def test_empty_rows():
    """Пустой ввод — пустой результат, не падать."""
    assert aggregate_realization_rows([]) == {}


def test_bonus_means_seller_minus_customer():
    """В Ozon: bonus = СПП-компенсация = seller_price − customer_price.
    Проверяем что мы это правильно сохраняем (для последующей проверки в UI)."""
    rows = [_row(100, cp=1500.0, qty=10, sp=2500.0, bonus=10000.0)]
    # sp=2500, cp=1500, qty=10 → spp_per_unit=1000, total bonus = 10000 ✓
    result = aggregate_realization_rows(rows)
    agg = result[100]
    assert agg.sum_bonus == 10000.0
    # Контроль: avg(sp − cp) ≈ bonus / qty
    assert (agg.weighted_sp - agg.weighted_cp) == pytest.approx(1000.0)
