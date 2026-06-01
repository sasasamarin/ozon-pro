"""Тесты на TokenBucket — fundament rate-limit'а для всех Ozon API клиентов."""
from __future__ import annotations

import asyncio
import time

import pytest
from app.services.ozon_client import TokenBucket, _parse_retry_after


@pytest.mark.asyncio
async def test_burst_within_capacity_no_wait():
    """Burst в пределах capacity — мгновенно."""
    bucket = TokenBucket(rate=10.0, capacity=5)
    start = time.monotonic()
    for _ in range(5):
        await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05, f"5 запросов burst должны быть мгновенно, было {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_excess_waits_for_refill():
    """Если burst исчерпан, 6-й запрос должен ждать ~1/rate секунды."""
    bucket = TokenBucket(rate=10.0, capacity=2)  # 10 tokens/sec, burst 2
    await bucket.acquire()
    await bucket.acquire()
    # capacity исчерпан; следующий должен подождать ~0.1с
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert 0.07 < elapsed < 0.25, f"6-й запрос ждал {elapsed:.3f}s, ожидаемо ~0.1s"


@pytest.mark.asyncio
async def test_refill_over_time():
    """После паузы tokens восстанавливаются."""
    bucket = TokenBucket(rate=20.0, capacity=2)
    # Истощаем
    await bucket.acquire()
    await bucket.acquire()
    # Спим 0.2с → за это время накопится 4 токена, ограничено capacity=2
    await asyncio.sleep(0.2)
    start = time.monotonic()
    await bucket.acquire()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05, f"После паузы 2 burst должны быть мгновенно, было {elapsed:.3f}s"


def test_parse_retry_after_seconds():
    """Стандартный формат — секунды как число."""
    assert _parse_retry_after("5") == 5.0
    assert _parse_retry_after("0.5") == 0.5
    assert _parse_retry_after("120") == 120.0


def test_parse_retry_after_none_or_invalid():
    """None / пусто / HTTP-date — None."""
    assert _parse_retry_after(None) is None
    assert _parse_retry_after("") is None
    assert _parse_retry_after("Wed, 21 Oct 2025 07:28:00 GMT") is None


def test_parse_retry_after_zero_returns_zero():
    """Retry-After=0 — валидно, но в _rate_limit_wait потом ограничится до 1с."""
    assert _parse_retry_after("0") == 0.0


def test_parse_retry_after_negative_invalid():
    """Отрицательный Retry-After — невалид, None."""
    assert _parse_retry_after("-5") is None
