"""
Матрица метрика×день (nepsell-канон): выбранные метрики × выбранные дни.

GET /api/v1/analytics/metrics-matrix?days=28&metrics=impressions,clicks,orders,...
&product_id=...&cabinet_ids=...&granularity=day|week|month

Возвращает массив строк {date, metric1, metric2, ...} — готово для таблицы и графика.
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import AdStatistics, AnalyticsDaily, OzonAccount, Product, User

router = APIRouter()
UTC = timezone.utc

# Перечень всех доступных метрик — выкатываем то что есть в БД
AVAILABLE_METRICS = [
    # Трафик
    {"key": "impressions",        "label": "Показы",                "group": "Трафик"},
    {"key": "impressions_search", "label": "Показы в поиске",       "group": "Трафик"},
    {"key": "impressions_pdp",    "label": "Показы на карточке",    "group": "Трафик"},
    {"key": "card_visits",        "label": "Посещения карточки",    "group": "Клики"},
    {"key": "ctr_pct",            "label": "CTR показ→карточка %",  "group": "Клики"},
    # Корзина / заказ
    {"key": "to_cart_search",     "label": "В корзину (поиск)",     "group": "Корзина"},
    {"key": "to_cart_pdp",        "label": "В корзину (карточка)",  "group": "Корзина"},
    {"key": "orders",             "label": "Заказы",                "group": "Заказы"},
    {"key": "ordered_revenue",    "label": "Сумма заказов",         "group": "Заказы"},
    {"key": "cart_to_order_pct",  "label": "Конверсия корзина→заказ %", "group": "Заказы"},
    # Выкуп
    {"key": "delivered",          "label": "Выкуплено",             "group": "Выкуп"},
    {"key": "returns",            "label": "Возвраты",              "group": "Выкуп"},
    {"key": "cancellations",      "label": "Отмены",                "group": "Выкуп"},
    # Реклама
    {"key": "ad_impressions",     "label": "Рекл. показы",          "group": "Реклама"},
    {"key": "ad_clicks",          "label": "Рекл. клики",           "group": "Реклама"},
    {"key": "ad_orders",          "label": "Рекл. заказы",          "group": "Реклама"},
    {"key": "ad_spend",           "label": "Расход на рекламу",     "group": "Реклама"},
    {"key": "ad_drr_pct",         "label": "ДРР % (от выручки)",    "group": "Реклама"},
]


class MetricInfo(BaseModel):
    key: str
    label: str
    group: str


class MatrixRow(BaseModel):
    date: str
    values: dict[str, float | None]


class MatrixResp(BaseModel):
    period_from: str
    period_to: str
    granularity: str
    metrics: list[MetricInfo]
    rows: list[MatrixRow]


@router.get("/available", response_model=list[MetricInfo])
async def list_available_metrics() -> list[MetricInfo]:
    return [MetricInfo(**m) for m in AVAILABLE_METRICS]


@router.get("/", response_model=MatrixResp)
async def get_metrics_matrix(
    days: int = Query(28, ge=1, le=365),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    granularity: str = Query("day", regex="^(day|week|month)$"),
    metrics: list[str] | None = Query(None, description="Список метрик через повторяющийся параметр"),
    product_id: uuid.UUID | None = Query(None),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MatrixResp:
    today = datetime.now(UTC).date()
    if not date_to: date_to = today
    if not date_from: date_from = date_to - timedelta(days=days)

    # Защита: только метрики из allowlist
    avail_keys = {m["key"] for m in AVAILABLE_METRICS}
    selected = [m for m in (metrics or ["impressions", "orders", "delivered", "ad_spend"]) if m in avail_keys]
    if not selected:
        selected = ["impressions", "orders"]

    # Кабинеты компании
    cab_q = select(OzonAccount.id).where(
        OzonAccount.company_id == current_user.company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if cabinet_ids:
        cab_q = cab_q.where(OzonAccount.id.in_(cabinet_ids))
    accs = [r[0] for r in (await db.execute(cab_q)).all()]
    if not accs:
        return MatrixResp(
            period_from=date_from.isoformat(), period_to=date_to.isoformat(),
            granularity=granularity,
            metrics=[MetricInfo(**m) for m in AVAILABLE_METRICS if m["key"] in selected],
            rows=[],
        )

    # date trunc для group по гранулярности
    trunc = {"day": "day", "week": "week", "month": "month"}[granularity]

    # Базовая агрегация AnalyticsDaily
    ad_where = [
        Product.ozon_account_id.in_(accs),
        AnalyticsDaily.date >= date_from,
        AnalyticsDaily.date <= date_to,
    ]
    if product_id is not None:
        ad_where.append(AnalyticsDaily.product_id == product_id)

    ad_rows = (await db.execute(
        select(
            func.date_trunc(trunc, AnalyticsDaily.date).label("d"),
            func.sum(AnalyticsDaily.hits_view_search).label("imp_s"),
            func.sum(AnalyticsDaily.hits_view_pdp).label("imp_p"),
            func.sum(AnalyticsDaily.session_view_pdp).label("card_visits"),
            func.sum(AnalyticsDaily.hits_tocart_search).label("cart_s"),
            func.sum(AnalyticsDaily.hits_tocart_pdp).label("cart_p"),
            func.sum(AnalyticsDaily.ordered_units).label("orders"),
            func.sum(AnalyticsDaily.revenue).label("rev"),
            func.sum(AnalyticsDaily.delivered_units).label("delivered"),
            func.sum(AnalyticsDaily.returns).label("returns"),
            func.sum(AnalyticsDaily.cancellations).label("cancels"),
        )
        .select_from(AnalyticsDaily)
        .join(Product, Product.id == AnalyticsDaily.product_id)
        .where(*ad_where)
        .group_by("d").order_by("d")
    )).all()

    # Рекламные метрики
    ad_stat_where = [
        AdStatistics.ozon_account_id.in_(accs),
        AdStatistics.date >= date_from, AdStatistics.date <= date_to,
    ]
    if product_id is not None:
        ad_stat_where.append(AdStatistics.product_id == product_id)
    ad_stat_rows = (await db.execute(
        select(
            func.date_trunc(trunc, AdStatistics.date).label("d"),
            func.sum(AdStatistics.impressions).label("ad_imp"),
            func.sum(AdStatistics.clicks).label("ad_clk"),
            func.sum(AdStatistics.orders).label("ad_ord"),
            func.sum(AdStatistics.spend).label("ad_spend"),
        ).where(*ad_stat_where).group_by("d")
    )).all()
    ad_map = {r.d.date() if hasattr(r.d, "date") else r.d: r for r in ad_stat_rows}

    # Сборка матрицы
    out: list[MatrixRow] = []
    for r in ad_rows:
        d = r.d.date() if hasattr(r.d, "date") else r.d
        imp = int((r.imp_s or 0) + (r.imp_p or 0))
        cv = int(r.card_visits or 0)
        cart = int((r.cart_s or 0) + (r.cart_p or 0))
        orders = int(r.orders or 0)
        rev = float(r.rev or 0)
        delivered = int(r.delivered or 0)
        ad_row = ad_map.get(d)
        ad_imp = int(ad_row.ad_imp or 0) if ad_row else 0
        ad_spend = float(ad_row.ad_spend or 0) if ad_row else 0

        values = {
            "impressions": imp,
            "impressions_search": int(r.imp_s or 0),
            "impressions_pdp": int(r.imp_p or 0),
            "card_visits": cv,
            "ctr_pct": round(cv / imp * 100, 2) if imp else None,
            "to_cart_search": int(r.cart_s or 0),
            "to_cart_pdp": int(r.cart_p or 0),
            "orders": orders,
            "ordered_revenue": round(rev, 2),
            "cart_to_order_pct": round(orders / cart * 100, 2) if cart else None,
            "delivered": delivered,
            "returns": int(r.returns or 0),
            "cancellations": int(r.cancels or 0),
            "ad_impressions": ad_imp,
            "ad_clicks": int(ad_row.ad_clk or 0) if ad_row else 0,
            "ad_orders": int(ad_row.ad_ord or 0) if ad_row else 0,
            "ad_spend": round(ad_spend, 2),
            "ad_drr_pct": round(ad_spend / rev * 100, 2) if rev else None,
        }
        # Берём только выбранные метрики
        out.append(MatrixRow(date=d.isoformat(), values={k: values.get(k) for k in selected}))

    return MatrixResp(
        period_from=date_from.isoformat(), period_to=date_to.isoformat(),
        granularity=granularity,
        metrics=[MetricInfo(**m) for m in AVAILABLE_METRICS if m["key"] in selected],
        rows=out,
    )
