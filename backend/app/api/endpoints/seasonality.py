"""
/api/v1/seasonality/* — сезонный анализ (см. brief: «Раздел Сезонность»).

Принципы:
- Источник A = своя история SKU/кабинета (order_items)
- Источник B = категорийный агрегат кабинета через Ozon /v1/analytics/data
- Каждое число помечено source-флагом. A и B не смешиваем.
- Gating по объёму истории: <90 / 90-364 / 365-729 / 730+ дней.
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.deps_cabinets import get_accessible_cabinet_ids, verify_cabinet_access
from app.db.session import get_db
from app.models import OzonAccount, Product, User
from app.services.seasonality import events as events_module
from app.services.seasonality import source_a, source_b


router = APIRouter()


# === Schemas ================================================================


class ConfidenceBlock(BaseModel):
    days_history: int
    confidence: str       # high | medium | low | insufficient
    note: str
    yoy_full_years: int


class ProfileResp(BaseModel):
    source: str           # 'own_sales' | 'cabinet_category_aggregate'
    confidence: ConfidenceBlock
    metric: str
    granularity: str
    buckets: list[dict]
    annual_avg: float
    based_on_months: int | None = None
    unavailable_reason: str | None = None  # 'rate_limit_ozon' | None — для Source B


class YoyResp(BaseModel):
    source: str
    confidence: ConfidenceBlock
    metric: str
    years: list[int]
    series: list[dict]


class DetectItem(BaseModel):
    product_id: str
    name: str | None
    offer_id: str | None
    ozon_sku: int | None
    days_history: int
    confidence: str
    verdict: str          # seasonal | flat | insufficient
    peak_month: int | None
    amplitude_ratio: float | None


class DetectResp(BaseModel):
    items: list[DetectItem]


class ForecastRow(BaseModel):
    year: int
    month: int
    seasonal_index: float | None
    forecast_units: float | None


class ForecastResp(BaseModel):
    source: str           # 'model' — оценка
    confidence: ConfidenceBlock
    base_monthly: float | None
    rows: list[ForecastRow]


# === Helpers ================================================================


async def _resolve_cabinet(
    db: AsyncSession, current_user: User, cabinet_id: uuid.UUID | None,
) -> uuid.UUID:
    """Выбираем кабинет: явный (с проверкой company), либо первый активный."""
    if cabinet_id:
        ok = (await db.execute(select(OzonAccount.id).where(
            OzonAccount.id == cabinet_id,
            OzonAccount.company_id == current_user.company_id,
        ))).scalar_one_or_none()
        if not ok:
            raise HTTPException(404, "Кабинет не найден или не ваш")
        await verify_cabinet_access(db, current_user, cabinet_id)
        return ok
    accessible = await get_accessible_cabinet_ids(db, current_user)
    first_q = select(OzonAccount.id).where(
        OzonAccount.company_id == current_user.company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if accessible is not None:
        first_q = first_q.where(OzonAccount.id.in_(accessible))
    first = (await db.execute(first_q.limit(1))).scalar_one_or_none()
    if not first:
        raise HTTPException(404, "Нет активных кабинетов")
    return first


async def _verify_product(
    db: AsyncSession, current_user: User, product_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Проверка что product принадлежит компании юзера. Возвращает (pid, cabinet_id)."""
    p = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Товар не найден")
    acc = (await db.execute(select(OzonAccount.company_id).where(
        OzonAccount.id == p.ozon_account_id,
    ))).scalar_one_or_none()
    if acc != current_user.company_id:
        raise HTTPException(403, "Товар чужого кабинета")
    # RBAC: если у юзера ограниченный MAA — проверяем доступ к кабинету товара
    accessible = await get_accessible_cabinet_ids(db, current_user)
    if accessible is not None and p.ozon_account_id not in accessible:
        raise HTTPException(403, "Нет доступа к этому кабинету")
    return p.id, p.ozon_account_id


def _confidence_block(hs) -> ConfidenceBlock:
    return ConfidenceBlock(
        days_history=hs.days_history,
        confidence=hs.confidence,
        note=hs.confidence_note,
        yoy_full_years=hs.yoy_full_years,
    )


# === ПРОФИЛЬ (индексы по месяцу/неделе) =====================================


@router.get("/profile", response_model=ProfileResp)
async def get_profile(
    product_id: uuid.UUID | None = Query(None),
    cabinet_id: uuid.UUID | None = Query(None),
    metric: Literal["orders", "buyouts", "revenue"] = "buyouts",
    granularity: Literal["month", "week"] = "month",
    source_pref: Literal["auto", "own", "category"] = "auto",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResp:
    """Сезонный профиль: индекс на bucket / среднегодовой.

    source_pref:
      auto — A если ≥365 дней истории, иначе B (категория кабинета)
      own  — всегда A
      category — всегда B (требует cabinet_id)
    """
    # Решаем кабинет (нужен для B и для проверки product)
    cab_id = None
    pid = None
    if product_id:
        pid, cab_id = await _verify_product(db, current_user, product_id)
    else:
        cab_id = await _resolve_cabinet(db, current_user, cabinet_id)

    # История
    hs = (await source_a.history_for_product(db, pid)) if pid else \
         (await source_a.history_for_cabinet(db, cab_id))

    # Выбор источника
    use_source = source_pref
    if source_pref == "auto":
        use_source = "own" if hs.days_history >= 365 else "category"

    if use_source == "own":
        data = await source_a.profile(
            db, product_id=pid, cabinet_id=None if pid else cab_id,
            metric=metric, granularity=granularity,
        )
        return ProfileResp(
            source="own_sales", confidence=_confidence_block(hs),
            metric=metric, granularity=granularity,
            buckets=data["buckets"], annual_avg=data["annual_avg"],
        )

    # B — категория кабинета. Только monthly (Ozon отдаёт месячно).
    if granularity != "month":
        # Перепадаем на own даже если истории мало — недельный B недоступен
        data = await source_a.profile(
            db, product_id=pid, cabinet_id=None if pid else cab_id,
            metric=metric, granularity="week",
        )
        return ProfileResp(
            source="own_sales", confidence=_confidence_block(hs),
            metric=metric, granularity="week",
            buckets=data["buckets"], annual_avg=data["annual_avg"],
        )

    b_metric = "revenue" if metric == "revenue" else "ordered_units"
    data = await source_b.profile_from_category(db, account_id=cab_id, metric=b_metric)
    return ProfileResp(
        source="cabinet_category_aggregate",
        confidence=_confidence_block(hs),
        metric=metric, granularity="month",
        buckets=data["buckets"], annual_avg=data["annual_avg"],
        based_on_months=data["based_on_months"],
        unavailable_reason=source_b.get_last_fail_reason(cab_id),
    )


# === YoY ====================================================================


@router.get("/yoy", response_model=YoyResp)
async def get_yoy(
    product_id: uuid.UUID | None = Query(None),
    cabinet_id: uuid.UUID | None = Query(None),
    metric: Literal["orders", "buyouts", "revenue"] = "buyouts",
    source_pref: Literal["auto", "own", "category"] = "auto",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> YoyResp:
    """YoY-наложение: ось X = day-of-year (own) или month (category)."""
    cab_id = None
    pid = None
    if product_id:
        pid, cab_id = await _verify_product(db, current_user, product_id)
    else:
        cab_id = await _resolve_cabinet(db, current_user, cabinet_id)

    hs = (await source_a.history_for_product(db, pid)) if pid else \
         (await source_a.history_for_cabinet(db, cab_id))

    use_source = source_pref
    if source_pref == "auto":
        use_source = "own" if hs.days_history >= 365 else "category"

    if use_source == "own":
        data = await source_a.yoy(
            db, product_id=pid, cabinet_id=None if pid else cab_id, metric=metric,
        )
        return YoyResp(
            source="own_sales", confidence=_confidence_block(hs),
            metric=metric, years=data["years"], series=data["series"],
        )

    b_metric = "revenue" if metric == "revenue" else "ordered_units"
    data = await source_b.yoy_from_category(db, account_id=cab_id, metric=b_metric)
    return YoyResp(
        source="cabinet_category_aggregate", confidence=_confidence_block(hs),
        metric=metric, years=data["years"], series=data["series"],
    )


# === Автодетект сезонных товаров ============================================


@router.get("/detect", response_model=DetectResp)
async def get_detect(
    cabinet_id: uuid.UUID | None = Query(None),
    metric: Literal["orders", "buyouts", "revenue"] = "buyouts",
    threshold_ratio: float = Query(1.5, ge=1.0, le=10.0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DetectResp:
    """Список SKU кабинета с меткой: seasonal/flat/insufficient + месяц пика."""
    cab_id = await _resolve_cabinet(db, current_user, cabinet_id)
    data = await source_a.detect_cabinet(
        db, cabinet_id=cab_id, metric=metric, threshold_ratio=threshold_ratio,
    )
    return DetectResp(items=data["items"])


# === Календарь событий ======================================================


@router.get("/events")
async def get_events(
    year: int | None = Query(None, ge=2024, le=2030),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Список сезонных событий (РФ + Ozon-распродажи)."""
    if date_from and date_to:
        return events_module.events_in_range(date_from, date_to)
    y = year or date_cls.today().year
    return events_module.events_for_year(y)


# === Прогноз пика ===========================================================


@router.get("/forecast", response_model=ForecastResp)
async def get_forecast(
    product_id: uuid.UUID = Query(...),
    metric: Literal["orders", "buyouts", "revenue"] = "buyouts",
    horizon_months: int = Query(12, ge=3, le=24),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ForecastResp:
    """Прогноз пика на горизонт. source='model' (оценка). Без истории → пусто."""
    pid, _ = await _verify_product(db, current_user, product_id)
    hs = await source_a.history_for_product(db, pid)
    data = await source_a.forecast_peak(
        db, product_id=pid, metric=metric, horizon_months=horizon_months,
    )
    return ForecastResp(
        source=data["source"],
        confidence=_confidence_block(hs),
        base_monthly=data.get("base_monthly"),
        rows=[ForecastRow(**r) for r in data["rows"]],
    )
