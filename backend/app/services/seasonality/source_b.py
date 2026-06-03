"""
Source B — категорийный агрегат кабинета через Ozon /v1/analytics/data.

Probe Premium API (2026-06-03) подтвердил:
- dimension=["category","month"] → 200, отдаёт СВОЙ агрегат помесячно.
- Рыночная ниша / search-queries → 404 на Premium Plus (нужен Premium Pro).

→ Source B = «категория в ВАШЕМ кабинете» (агрегат своих SKU той же
категории за глубокую историю). Не настоящая ниша Ozon-рынка, но честно
подписано «по категории вашего кабинета».

Кэш: in-process LRU с TTL 24h (категории меняются редко).
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import log
from app.core.security import decrypt_secret
from app.models import OzonAccount
from app.services.ozon_client import OzonSellerClient


Metric = Literal["revenue", "ordered_units"]

# Кэш категорийных рядов (account_id, metric) → (ts, data)
_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_CACHE_TTL = 24 * 3600  # 24 часа
_LOCK = asyncio.Lock()


async def _fetch_category_monthly(
    db: AsyncSession, *, account_id: uuid.UUID, metric: Metric,
    date_from: str, date_to: str,
) -> list[dict]:
    """Один вызов /v1/analytics/data с dimension=['category','month']."""
    acc = (await db.execute(
        select(OzonAccount).where(OzonAccount.id == account_id)
    )).scalar_one_or_none()
    if not acc:
        return []
    cid = decrypt_secret(acc.client_id_encrypted)
    apk = decrypt_secret(acc.api_key_encrypted)

    async with OzonSellerClient(cid, apk) as client:
        try:
            resp = await client._client.post(
                "/v1/analytics/data",
                json={
                    "date_from": date_from, "date_to": date_to,
                    "dimension": ["category", "month"],
                    "metrics": [metric, "ordered_units"],
                    "limit": 1000,
                },
                headers={
                    "Client-Id": cid, "Api-Key": apk,
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code != 200:
                log.warning("source_b_fetch_failed",
                            status=resp.status_code, body=resp.text[:200])
                return []
            j = resp.json().get("result", {}).get("data", [])
            return j
        except Exception as e:
            log.exception("source_b_fetch_exception", err=str(e))
            return []


async def category_monthly(
    db: AsyncSession, *,
    account_id: uuid.UUID, metric: Metric = "ordered_units",
    date_from: str = "2024-01-01",
    date_to: str | None = None,
) -> list[dict]:
    """
    Возвращает [{ym: '2025-01', value: 10692374, count: 1173}, ...]
    из категорийного агрегата кабинета. Кэшируется 24ч.

    На фронте используется как Source B для fallback, когда у SKU
    собственной истории мало (<365 дней).
    """
    from datetime import date as date_cls
    if not date_to:
        date_to = date_cls.today().isoformat()
    key = (str(account_id), metric)
    now = time.time()

    async with _LOCK:
        hit = _CACHE.get(key)
        if hit and (now - hit[0]) < _CACHE_TTL:
            return hit[1]["rows"]

        raw = await _fetch_category_monthly(
            db, account_id=account_id, metric=metric,
            date_from=date_from, date_to=date_to,
        )
        # Парсим в плоский формат
        rows = []
        for item in raw:
            dims = item.get("dimensions", [])
            metrics = item.get("metrics", [])
            if not dims or len(metrics) < 1:
                continue
            ym = dims[0].get("id")  # 'YYYY-MM'
            value = float(metrics[0] or 0)
            count = float(metrics[1] or 0) if len(metrics) > 1 else 0
            if ym and "-" in ym and len(ym) == 7:
                rows.append({"ym": ym, "value": value, "count": count})
        rows.sort(key=lambda x: x["ym"])
        _CACHE[key] = (now, {"rows": rows})
        return rows


async def profile_from_category(
    db: AsyncSession, *,
    account_id: uuid.UUID, metric: Metric = "ordered_units",
) -> dict:
    """
    Сезонный профиль из категорийного агрегата — индекс на месяц года (1..12).
    Используется как fallback для SKU с малой собственной историей.
    """
    rows = await category_monthly(db, account_id=account_id, metric=metric)
    by_month: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    for r in rows:
        try:
            _, m = r["ym"].split("-")
            by_month[int(m)].append(r["value"])
        except (ValueError, KeyError):
            continue
    monthly_avg = {m: (sum(v) / len(v) if v else 0) for m, v in by_month.items()}
    overall_avg = sum(monthly_avg.values()) / 12 if any(monthly_avg.values()) else 0
    buckets = []
    for m in range(1, 13):
        v = monthly_avg[m]
        buckets.append({
            "bucket": m, "value": round(v, 2),
            "index": round(v / overall_avg, 3) if overall_avg else None,
            "years_seen": len(by_month[m]),
        })
    return {
        "buckets": buckets,
        "annual_avg": round(overall_avg, 2),
        "based_on_months": len(rows),
    }


async def yoy_from_category(
    db: AsyncSession, *,
    account_id: uuid.UUID, metric: Metric = "ordered_units",
) -> dict:
    """YoY-формат для категорийного агрегата: ось X = месяц года, линии = годы."""
    rows = await category_monthly(db, account_id=account_id, metric=metric)
    years = sorted({int(r["ym"].split("-")[0]) for r in rows})
    by_month: dict[int, dict] = {}
    for r in rows:
        y, m = r["ym"].split("-")
        d = by_month.setdefault(int(m), {"month": int(m)})
        d[y] = r["value"]
    series = [by_month[m] for m in sorted(by_month.keys())]
    return {"years": years, "series": series}
