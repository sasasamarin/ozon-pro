"""
/api/v1/competitor — конкурентный сигнал из Premium Plus.

Прямой конкурентной аналитики (search-queries, brand-engagement) Ozon
не отдаёт на Premium Plus (см. probe 2026-06-04, все 17 endpoints → 404).

ПОЭТОМУ строим КОСВЕННЫЕ сигналы из того что есть:
- unique_search_users (product_queries_daily) — поисковый интерес к нише
- unique_view_users — кто реально открыл карточку = эффективность миниатюры
- view_conversion = unique_view / unique_search — насколько мы привлекательны
- gmv per unique_search_user — деньги с одного поискового юзера
- position_category (analytics_daily) — наша позиция в категории по дням
- ad_imp_share — доля платного трафика (вынуждены платить = конкуренция)
- СПП-индикатор (seller − customer_avg) — рынок «давит» цену

Если у одного из них тренд вниз → конкуренты нас обходят.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.deps_cabinets import verify_cabinet_access
from app.db.session import get_db
from app.models import User


router = APIRouter()


class SignalPoint(BaseModel):
    date: str
    unique_search: int | None
    unique_view: int | None
    view_conversion_pct: float | None
    gmv_rub: float | None
    position_category: float | None
    ad_imp_share_pct: float | None
    spp_pct: float | None
    revenue_rub: float | None


class TrendSummary(BaseModel):
    metric: str
    first_value: float | None
    last_value: float | None
    change_pct: float | None
    direction: str       # 'up' | 'down' | 'flat'
    verdict: str         # interpretation для пользователя


class CompetitorSignal(BaseModel):
    product_id: str
    product_name: str | None
    period_from: str
    period_to: str
    series: list[SignalPoint]
    trends: list[TrendSummary]
    confidence: str       # 'high' | 'medium' | 'low' — по длине истории
    note: str


def _trend(first: float | None, last: float | None,
           metric: str, *, lower_is_better: bool = False) -> TrendSummary:
    if first is None or last is None or first == 0:
        return TrendSummary(
            metric=metric, first_value=first, last_value=last,
            change_pct=None, direction='flat',
            verdict='Недостаточно данных',
        )
    pct = (last - first) / abs(first) * 100
    if abs(pct) < 5:
        direction = 'flat'
    elif pct > 0:
        direction = 'up'
    else:
        direction = 'down'

    # Семантический verdict
    is_good = (direction == 'up') if not lower_is_better else (direction == 'down')
    if direction == 'flat':
        verdict = 'без изменений'
    elif is_good:
        verdict = f'улучшение на {abs(pct):.1f}%'
    else:
        verdict = f'ухудшение на {abs(pct):.1f}% — следить'
    return TrendSummary(
        metric=metric, first_value=round(first, 2), last_value=round(last, 2),
        change_pct=round(pct, 2), direction=direction, verdict=verdict,
    )


@router.get("/signal", response_model=CompetitorSignal)
async def competitor_signal(
    product_id: uuid.UUID = Query(...),
    days: int = Query(30, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompetitorSignal:
    """Конкурентный сигнал по одному SKU за период."""
    p = (await db.execute(text("""
        SELECT p.id::text id, p.name, p.ozon_account_id::text cab_id,
               p.marketing_price, p.avg_customer_price_30d
        FROM products p JOIN ozon_accounts oa ON oa.id = p.ozon_account_id
        WHERE p.id = :pid AND oa.company_id = :cid
    """), {"pid": str(product_id), "cid": str(current_user.company_id)})).first()
    if not p:
        raise HTTPException(404, "Товар не найден")

    # Cabinet isolation: проверяем что кабинет товара доступен юзеру
    await verify_cabinet_access(db, current_user, p.cab_id)

    df = date.today() - timedelta(days=days)
    dt = date.today()

    # Тянем все сигналы одним запросом — JOIN дневных таблиц по дате
    rows = (await db.execute(text("""
        WITH days AS (
            SELECT generate_series(:df::date, :dt::date, '1 day')::date AS d
        ),
        pq AS (
            SELECT date, SUM(unique_search_users) usu, SUM(unique_view_users) uvu,
                   SUM(gmv) gmv,
                   CASE WHEN SUM(unique_search_users) > 0
                        THEN SUM(unique_view_users)::float / SUM(unique_search_users) * 100
                        ELSE NULL END AS view_conv
            FROM product_queries_daily
            WHERE product_id = :pid AND date BETWEEN :df AND :dt
            GROUP BY date
        ),
        ad AS (
            SELECT date,
                   AVG(COALESCE(position_category, 0))::float AS pos_cat,
                   SUM(COALESCE(hits_view_search,0)) imp,
                   SUM(COALESCE(revenue,0)) rev
            FROM analytics_daily
            WHERE product_id = :pid AND date BETWEEN :df AND :dt
            GROUP BY date
        ),
        ads AS (
            SELECT date, SUM(impressions) ad_imp
            FROM ad_statistics
            WHERE product_id = :pid AND date BETWEEN :df AND :dt
            GROUP BY date
        )
        SELECT d.d AS date,
               pq.usu, pq.uvu, pq.view_conv, pq.gmv,
               ad.pos_cat,
               ad.imp AS total_imp, ads.ad_imp,
               ad.rev,
               CASE WHEN ad.imp > 0 AND ads.ad_imp IS NOT NULL
                    THEN ads.ad_imp::float / ad.imp * 100
                    ELSE NULL END AS ad_share_pct
        FROM days d
        LEFT JOIN pq ON pq.date = d.d
        LEFT JOIN ad ON ad.date = d.d
        LEFT JOIN ads ON ads.date = d.d
        ORDER BY d.d
    """), {"pid": str(product_id), "df": df, "dt": dt})).all()

    seller = float(p.marketing_price or 0)
    buyer_avg = float(p.avg_customer_price_30d or 0)
    spp_pct = ((seller - buyer_avg) / seller * 100) if seller and buyer_avg else None

    series: list[SignalPoint] = []
    for r in rows:
        series.append(SignalPoint(
            date=r.date.isoformat(),
            unique_search=int(r.usu) if r.usu else None,
            unique_view=int(r.uvu) if r.uvu else None,
            view_conversion_pct=round(float(r.view_conv), 2) if r.view_conv else None,
            gmv_rub=round(float(r.gmv), 2) if r.gmv else None,
            position_category=round(float(r.pos_cat), 1) if r.pos_cat else None,
            ad_imp_share_pct=round(float(r.ad_share_pct), 2) if r.ad_share_pct else None,
            spp_pct=spp_pct,
            revenue_rub=round(float(r.rev), 2) if r.rev else None,
        ))

    # Тренды (первое непустое vs последнее непустое значение)
    def _first_last(attr: str) -> tuple[float | None, float | None]:
        vals = [getattr(p, attr) for p in series if getattr(p, attr) is not None]
        if not vals:
            return None, None
        return vals[0], vals[-1]

    fs, ls = _first_last('unique_search')
    fv, lv = _first_last('unique_view')
    fc, lc = _first_last('view_conversion_pct')
    fp, lp = _first_last('position_category')
    fa, la = _first_last('ad_imp_share_pct')
    fr, lr = _first_last('revenue_rub')

    trends = [
        _trend(fs, ls, 'Поисковый интерес (unique_search)'),
        _trend(fv, lv, 'Привлекательность карточки (unique_view)'),
        _trend(fc, lc, 'Конверсия поиск→карточка (%)'),
        _trend(fp, lp, 'Позиция в категории', lower_is_better=True),
        _trend(fa, la, 'Доля платного трафика (%)', lower_is_better=True),
        _trend(fr, lr, 'Выручка из аналитики, ₽'),
    ]

    days_with_data = sum(1 for s in series if s.unique_search or s.revenue_rub)
    confidence = (
        'high' if days_with_data >= 21
        else 'medium' if days_with_data >= 7
        else 'low'
    )
    return CompetitorSignal(
        product_id=p.id, product_name=p.name,
        period_from=df.isoformat(), period_to=dt.isoformat(),
        series=series, trends=trends, confidence=confidence,
        note=(
            'Прямая конкурентная аналитика (search queries рынка) доступна '
            'на Premium Pro. На Premium Plus строим КОСВЕННЫЕ сигналы. '
            f'Дней с данными: {days_with_data}/{days}.'
        ),
    )
