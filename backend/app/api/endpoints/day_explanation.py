"""
«Объяснение дня» — почему именно в этот день метрики такие.

Юзер тычет в день на графике → панель с детерминированным разбором:
- Что было с показами/кликами/корзиной/заказами/выкупом в этот день
- Как это соотносится со средними за период (z-score)
- Реклама: крутилась? расход? ДРР?
- Цена продажи: была ли selling_price или Ozon снижал
- Остаток: были товары на складах?
- Список факторов (стокаут / просадка конверсии / просадка показов / реклама off / цена просела)
- Связный текст-вывод

БЕЗ AI — на детерминированных данных. AI-советник будет поверх.
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls, datetime, timedelta, timezone
from statistics import mean, median, stdev

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.deps_cabinets import get_accessible_cabinet_ids
from app.db.session import get_db
from app.models import (
    AdStatistics,
    AnalyticsDaily,
    OrderItem,
    OzonAccount,
    Product,
    User,
)
from app.models.order import Order

router = APIRouter()
UTC = timezone.utc


class DayMetrics(BaseModel):
    """Сырые метрики дня."""
    impressions: int                 # hits_view (Ozon UI), fallback search+pdp
    impressions_search: int          # hits_view_search
    card_visits: int                 # session_view_pdp
    orders: int                      # ordered_units
    revenue: float                   # revenue (если AnalyticsDaily есть), иначе sum oi.price × qty
    delivered: int                   # delivered_units
    returns: int                     # returns
    cancellations: int               # cancellations

    # Цена продажи
    avg_sold_price: float | None     # средний oi.price дня — если Ozon снижал СПП, увидим
    seller_price: float | None       # текущая selling_price (из карточки)
    price_dropped_pct: float | None  # насколько ниже текущего selling_price (если >0 — Ozon снизил цену)
    # «Оплачено покупателем» с СПП/Ozon-Картой за этот день (среднее по customer_price)
    avg_customer_price: float | None = None
    customer_spp_pct: float | None = None  # размер СПП в %: 1 − customer_price / seller_price

    # Реклама
    ad_impressions: int
    ad_clicks: int
    ad_orders: int
    ad_revenue: float
    ad_spend: float
    ad_drr_pct: float | None

    # Остаток (на конец дня)
    stock_total: int
    stockout: bool                   # был ли стокаут в этот день (free_to_sell == 0)

    # Конверсии
    cr_search_to_card_pct: float | None    # session_view_pdp / session_view_search × 100
    cr_card_to_order_pct: float | None     # ordered_units / card_visits × 100


class DayFactor(BaseModel):
    type: str                         # stockout | ads_off | price_drop | cr_drop | impressions_drop | high_drr | normal
    severity: str                     # high | medium | low | info
    title: str                        # короткий заголовок
    text: str                         # объяснение


class DayExplanation(BaseModel):
    date: date_cls
    product_id: str | None
    product_name: str | None

    day: DayMetrics
    # Средние/медианы за period_days (без выбранного дня)
    period_avg: dict[str, float]
    period_median: dict[str, float]
    # z-score метрик дня относительно периода (negative = ниже среднего)
    z_scores: dict[str, float | None]

    factors: list[DayFactor]
    summary: str                      # связный текст-вывод


def _z(value: float, mu: float, sigma: float) -> float | None:
    if sigma is None or sigma == 0:
        return None
    return round((value - mu) / sigma, 2)


def _stats(values: list[float]) -> tuple[float, float, float]:
    """(mean, median, stdev). Возвращает 0.0 для stdev если выборка < 2."""
    if not values:
        return 0.0, 0.0, 0.0
    m = mean(values)
    md = median(values)
    sd = stdev(values) if len(values) >= 2 else 0.0
    return m, md, sd


@router.get("/", response_model=DayExplanation)
async def explain_day(
    date: date_cls = Query(..., description="Целевой день (YYYY-MM-DD)"),
    product_id: uuid.UUID | None = Query(None, description="Если не задан — агрегат по всем товарам компании."),
    period_days: int = Query(28, ge=7, le=90, description="Сколько дней брать в сравнение со средним."),
    cabinet_ids: list[uuid.UUID] | None = Query(None, description="Фильтр кабинетов; пусто = все кабинеты компании."),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DayExplanation:
    # ─── Базовые границы кабинетов компании юзера ──────────────────────────
    accessible = await get_accessible_cabinet_ids(db, current_user)
    cab_q = select(OzonAccount.id).where(
        OzonAccount.company_id == current_user.company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if accessible is not None:
        cab_q = cab_q.where(OzonAccount.id.in_(accessible))
    if cabinet_ids:
        cab_q = cab_q.where(OzonAccount.id.in_(cabinet_ids))
    cab_rows = (await db.execute(cab_q)).all()
    allowed_cab_ids = [r[0] for r in cab_rows]

    # ─── Какие product_id участвуют в выборке ──────────────────────────────
    if product_id is not None:
        # Безопасность: товар должен быть в разрешённых кабинетах
        check = (await db.execute(
            select(Product.id, Product.name, Product.marketing_price, Product.current_price)
            .where(Product.id == product_id, Product.ozon_account_id.in_(allowed_cab_ids))
        )).first()
        if check is None:
            from fastapi import HTTPException
            raise HTTPException(404, "Product not found in user's cabinets")
        product_ids = [product_id]
        product_name = check.name
        seller_price = float(check.marketing_price or check.current_price or 0) or None
    else:
        prod_rows = (await db.execute(
            select(Product.id).where(Product.ozon_account_id.in_(allowed_cab_ids), Product.deleted_at.is_(None))
        )).all()
        product_ids = [r[0] for r in prod_rows]
        product_name = None
        seller_price = None

    period_from = date - timedelta(days=period_days)
    period_to = date  # exclusive верх (без целевого дня)

    # ─── Метрики из AnalyticsDaily — день + период ─────────────────────────
    ad_query = (
        select(
            AnalyticsDaily.date,
            func.sum(func.coalesce(
                AnalyticsDaily.hits_view,
                AnalyticsDaily.hits_view_search + AnalyticsDaily.hits_view_pdp,
            )).label("hits_total"),
            func.sum(AnalyticsDaily.hits_view_search).label("hits_search"),
            func.sum(AnalyticsDaily.hits_view_pdp).label("hits_pdp"),
            func.sum(AnalyticsDaily.session_view_pdp).label("sess_pdp"),
            func.sum(AnalyticsDaily.session_view_search).label("sess_search"),
            func.sum(AnalyticsDaily.ordered_units).label("orders_n"),
            func.sum(AnalyticsDaily.revenue).label("rev"),
            func.sum(AnalyticsDaily.delivered_units).label("delivered"),
            func.sum(AnalyticsDaily.returns).label("returns"),
            func.sum(AnalyticsDaily.cancellations).label("cancels"),
        )
        .where(
            AnalyticsDaily.product_id.in_(product_ids),
            AnalyticsDaily.date >= period_from,
            AnalyticsDaily.date <= date,
        )
        .group_by(AnalyticsDaily.date)
        .order_by(AnalyticsDaily.date)
    )
    rows = (await db.execute(ad_query)).all()
    by_date = {r.date: r for r in rows}
    target = by_date.get(date)
    others = [r for d, r in by_date.items() if d != date]

    # day metrics из AnalyticsDaily
    if target:
        impressions = int(target.hits_total or 0)  # «Показы всего» = hits_view (Ozon UI)
        impressions_search = int(target.hits_search or 0)
        card_visits = int(target.sess_pdp or 0)
        orders_n = int(target.orders_n or 0)
        revenue = float(target.rev or 0)
        delivered = int(target.delivered or 0)
        returns_n = int(target.returns or 0)
        cancels = int(target.cancels or 0)
    else:
        impressions = impressions_search = card_visits = orders_n = delivered = returns_n = cancels = 0
        revenue = 0.0

    cr_search_to_card = (
        round(card_visits / (int(target.sess_search or 0)) * 100, 2)
        if target and target.sess_search and int(target.sess_search) > 0 else None
    )
    cr_card_to_order = (
        round(orders_n / card_visits * 100, 2) if card_visits > 0 else None
    )

    # Период (без целевого дня)
    impressions_list = [int(r.hits_total or 0) for r in others]
    card_visits_list = [int(r.sess_pdp or 0) for r in others]
    orders_list = [int(r.orders_n or 0) for r in others]
    revenue_list = [float(r.rev or 0) for r in others]
    cr_card_to_order_list = [
        (int(r.orders_n or 0) / int(r.sess_pdp or 1) * 100) for r in others if int(r.sess_pdp or 0) > 0
    ]
    cr_search_to_card_list = [
        (int(r.sess_pdp or 0) / int(r.sess_search or 1) * 100) for r in others if int(r.sess_search or 0) > 0
    ]

    period_avg = {
        "impressions": round(mean(impressions_list), 1) if impressions_list else 0.0,
        "card_visits": round(mean(card_visits_list), 1) if card_visits_list else 0.0,
        "orders": round(mean(orders_list), 1) if orders_list else 0.0,
        "revenue": round(mean(revenue_list), 2) if revenue_list else 0.0,
        "cr_card_to_order_pct": round(mean(cr_card_to_order_list), 2) if cr_card_to_order_list else 0.0,
        "cr_search_to_card_pct": round(mean(cr_search_to_card_list), 2) if cr_search_to_card_list else 0.0,
    }
    period_median = {
        "impressions": round(median(impressions_list), 1) if impressions_list else 0.0,
        "card_visits": round(median(card_visits_list), 1) if card_visits_list else 0.0,
        "orders": round(median(orders_list), 1) if orders_list else 0.0,
        "revenue": round(median(revenue_list), 2) if revenue_list else 0.0,
        "cr_card_to_order_pct": round(median(cr_card_to_order_list), 2) if cr_card_to_order_list else 0.0,
        "cr_search_to_card_pct": round(median(cr_search_to_card_list), 2) if cr_search_to_card_list else 0.0,
    }
    imp_m, imp_md, imp_sd = _stats(impressions_list)
    cv_m, cv_md, cv_sd = _stats(card_visits_list)
    ord_m, ord_md, ord_sd = _stats(orders_list)
    rev_m, rev_md, rev_sd = _stats(revenue_list)
    cr1_m, cr1_md, cr1_sd = _stats(cr_search_to_card_list)
    cr2_m, cr2_md, cr2_sd = _stats(cr_card_to_order_list)

    z_scores = {
        "impressions": _z(impressions, imp_m, imp_sd),
        "card_visits": _z(card_visits, cv_m, cv_sd),
        "orders": _z(orders_n, ord_m, ord_sd),
        "revenue": _z(revenue, rev_m, rev_sd),
        "cr_search_to_card_pct": _z(cr_search_to_card or 0, cr1_m, cr1_sd) if cr_search_to_card is not None else None,
        "cr_card_to_order_pct": _z(cr_card_to_order or 0, cr2_m, cr2_sd) if cr_card_to_order is not None else None,
    }

    # ─── Реклама — AdStatistics за день ─────────────────────────────────────
    ad_query_where = [
        AdStatistics.ozon_account_id.in_(allowed_cab_ids),
        AdStatistics.date == date,
    ]
    if product_id is not None:
        ad_query_where.append(AdStatistics.product_id.in_(product_ids))
    ad_row = (await db.execute(
        select(
            func.coalesce(func.sum(AdStatistics.impressions), 0).label("imp"),
            func.coalesce(func.sum(AdStatistics.clicks), 0).label("clicks"),
            func.coalesce(func.sum(AdStatistics.orders), 0).label("orders"),
            func.coalesce(func.sum(AdStatistics.revenue), 0).label("revenue"),
            func.coalesce(func.sum(AdStatistics.spend), 0).label("spent"),
        ).where(*ad_query_where)
    )).first()

    ad_imp = int(ad_row.imp or 0)
    ad_clk = int(ad_row.clicks or 0)
    ad_ord = int(ad_row.orders or 0)
    ad_rev = float(ad_row.revenue or 0)
    ad_spend = float(ad_row.spent or 0)
    ad_drr = round(ad_spend / revenue * 100, 2) if revenue > 0 else None

    # ─── Средняя ФАКТИЧЕСКАЯ цена дня из order_items (если Ozon снижал — увидим) ───
    # + средняя customer_price (= цена покупателя с СПП) того же дня.
    avg_sold = None
    avg_customer = None
    if product_id is not None:
        op_row = (await db.execute(text("""
            SELECT AVG(oi.price)::float avg_p,
                   AVG(oi.customer_price)::float avg_cp,
                   COUNT(*) n
            FROM order_items oi JOIN orders o ON o.id = oi.order_id
            WHERE oi.product_id = :pid
              AND DATE(o.order_created_at) = :d
              AND oi.price > 0
        """), {"pid": str(product_id), "d": date})).first()
        avg_sold = float(op_row.avg_p) if op_row and op_row.avg_p else None
        avg_customer = float(op_row.avg_cp) if op_row and op_row.avg_cp else None

    price_dropped_pct = (
        round((seller_price - avg_sold) / seller_price * 100, 1)
        if (seller_price and avg_sold and seller_price > 0 and avg_sold < seller_price * 0.99)
        else None
    )
    # СПП-скидка покупателю: на сколько % customer_price ниже цены продавца
    customer_spp_pct = (
        round((1 - avg_customer / seller_price) * 100, 1)
        if (avg_customer and seller_price and seller_price > 0)
        else None
    )

    # ─── Остаток (stocks) — на КОНЕЦ дня (последний снапшот ≤ date+23:59) ───
    stock_total = 0
    stockout = False
    if product_id is not None:
        # asyncpg не любит `:d::date` подряд — передаём готовый datetime upper-bound
        end_dt = datetime.combine(date + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        stk_row = (await db.execute(text("""
          WITH last_snap AS (
            SELECT MAX(time) t FROM stocks
            WHERE product_id = :pid AND time < :end_dt
              AND warehouse_type IN ('FBO_WH', 'FBO', 'AGG')
          )
          SELECT COALESCE(SUM(GREATEST(s.free_to_sell - s.reserved, 0)), 0) total
          FROM stocks s, last_snap l
          WHERE s.product_id = :pid AND s.time = l.t
            AND s.warehouse_type IN ('FBO_WH', 'FBO', 'AGG')
        """), {"pid": str(product_id), "end_dt": end_dt})).first()
        stock_total = int(stk_row.total or 0) if stk_row else 0
        stockout = stock_total == 0

    day = DayMetrics(
        impressions=impressions,
        impressions_search=impressions_search,
        card_visits=card_visits,
        orders=orders_n,
        revenue=revenue,
        delivered=delivered,
        returns=returns_n,
        cancellations=cancels,
        avg_sold_price=avg_sold,
        seller_price=seller_price,
        price_dropped_pct=price_dropped_pct,
        avg_customer_price=avg_customer,
        customer_spp_pct=customer_spp_pct,
        ad_impressions=ad_imp,
        ad_clicks=ad_clk,
        ad_orders=ad_ord,
        ad_revenue=ad_rev,
        ad_spend=ad_spend,
        ad_drr_pct=ad_drr,
        stock_total=stock_total,
        stockout=stockout,
        cr_search_to_card_pct=cr_search_to_card,
        cr_card_to_order_pct=cr_card_to_order,
    )

    # ─── Факторы (детерминированные правила) ───────────────────────────────
    factors: list[DayFactor] = []

    # 1) Стокаут / Остаток
    if product_id is not None and stockout:
        factors.append(DayFactor(
            type="stockout", severity="high",
            title="Стокаут — нет товара на складах",
            text=f"На конец {date} остаток = 0. Без товара заказы физически невозможны.",
        ))
    elif product_id is not None and stock_total > 0 and stock_total <= 3:
        factors.append(DayFactor(
            type="stockout", severity="medium",
            title=f"Критический остаток ({stock_total} шт)",
            text=f"Остаток {stock_total} — товар может закончиться в любой момент, риск ускоренной просадки.",
        ))
    elif product_id is not None and stock_total > 3:
        factors.append(DayFactor(
            type="stock_ok", severity="info",
            title=f"Остаток {stock_total} шт — норма",
            text=f"На конец {date} на складах {stock_total} шт. Стокаут не был причиной этого дня.",
        ))

    # 2) Реклама выключена в день с историей рекламы
    avg_ad_spend_period = 0.0
    if product_ids:
        avg_ad_where = [
            AdStatistics.ozon_account_id.in_(allowed_cab_ids),
            AdStatistics.date >= period_from,
            AdStatistics.date < date,
        ]
        if product_id is not None:
            avg_ad_where.append(AdStatistics.product_id.in_(product_ids))
        avg_ad = (await db.execute(
            select(func.coalesce(func.sum(AdStatistics.spend), 0)).where(*avg_ad_where)
        )).scalar()
        avg_ad_spend_period = float(avg_ad or 0) / max(period_days - 1, 1)

    if ad_spend == 0 and avg_ad_spend_period > 100:
        factors.append(DayFactor(
            type="ads_off", severity="medium",
            title="Реклама не крутилась",
            text=f"Расход на рекламу = 0₽ (среднесуточно за период ≈ {avg_ad_spend_period:,.0f}₽). "
                 f"Без рекламного трафика органика просаживается.",
        ))

    # 3) Высокий ДРР
    if ad_drr is not None and ad_drr > 30:
        factors.append(DayFactor(
            type="high_drr", severity="medium",
            title=f"ДРР {ad_drr}% — высокий",
            text=f"Реклама съела {ad_drr}% выручки. Это снижает маржу.",
        ))

    # 4a) Цена покупателя с СПП (Ozon-Карта/Premium). Информационно, не финансы.
    if product_id is not None and avg_customer and customer_spp_pct and customer_spp_pct >= 5:
        factors.append(DayFactor(
            type="customer_spp", severity="info",
            title=f"Цена покупателя {avg_customer:,.0f}₽ (СПП −{customer_spp_pct}%)",
            text=f"Покупатели в этот день платили в среднем {avg_customer:,.0f}₽ (с учётом Ozon-СПП/Premium/баллов). "
                 f"На {customer_spp_pct}% ниже твоей цены {seller_price:,.0f}₽. На твою выручку это не влияет — "
                 f"начисление = твоя цена; но это драйвер спроса.",
        ))

    # 4b) Снижение цены продажи (Ozon крутил СПП самой ставки продавца)
    if price_dropped_pct and price_dropped_pct >= 1.5:
        factors.append(DayFactor(
            type="price_drop", severity="info",
            title=f"Ozon снизил цену на {price_dropped_pct}%",
            text=f"Средняя фактическая цена продажи в этот день: {avg_sold:,.0f}₽ "
                 f"(вместо обычной {seller_price:,.0f}₽). Это обычно поднимает спрос.",
        ))
    elif product_id is not None and avg_sold and seller_price and abs(avg_sold - seller_price) < seller_price * 0.015:
        # Positive confirmation: цена дня стандартная (СПП не крутили)
        factors.append(DayFactor(
            type="price_ok", severity="info",
            title=f"Цена дня стандартная ({avg_sold:,.0f}₽)",
            text=f"Ozon не крутил СПП-скидку, средняя фактическая = установленной цене продавца. "
                 f"Цена не была драйвером этого дня.",
        ))

    # 5) Просадка показов (z<-1.5)
    z_imp = z_scores.get("impressions")
    if z_imp is not None and z_imp <= -1.5 and impressions < imp_m:
        delta_pct = round((impressions - imp_m) / max(imp_m, 1) * 100, 0)
        factors.append(DayFactor(
            type="impressions_drop", severity="high",
            title=f"Показы упали {delta_pct:.0f}% к среднему",
            text=f"Показы {impressions:,} vs средние {imp_m:,.0f} за {period_days} дней. "
                 f"Возможные причины: позиция в выдаче упала, конкуренты обновили предложения, "
                 f"или товар выпал из акций Ozon.",
        ))

    # 6) Просадка конверсии корзина→заказ
    z_cr = z_scores.get("cr_card_to_order_pct")
    if cr_card_to_order is not None and z_cr is not None and z_cr <= -1.5 and card_visits >= 50:
        factors.append(DayFactor(
            type="cr_drop", severity="medium",
            title=f"Конверсия в заказ ниже нормы",
            text=f"CR карточка→заказ = {cr_card_to_order}% vs средние {cr2_m:.2f}%. "
                 f"Часто связано с ценой/отзывами/стоком в нужном регионе.",
        ))

    if not factors:
        factors.append(DayFactor(
            type="normal", severity="info",
            title="День в пределах нормы",
            text="Все ключевые метрики в пределах ±1.5σ от среднего за период. "
                 "Никаких аномалий-драйверов не обнаружено.",
        ))

    # ─── Сводный текст ─────────────────────────────────────────────────────
    parts = [f"{date.strftime('%d.%m')}: показы {impressions:,}, заказы {orders_n}, выручка {revenue:,.0f}₽."]
    high = [f for f in factors if f.severity == "high"]
    medium = [f for f in factors if f.severity == "medium"]
    if high:
        parts.append("Главное: " + "; ".join(f.title.lower() for f in high) + ".")
    elif medium:
        parts.append("Заметно: " + "; ".join(f.title.lower() for f in medium) + ".")
    else:
        parts.append("Без явных аномалий.")
    summary = " ".join(parts)

    return DayExplanation(
        date=date,
        product_id=str(product_id) if product_id else None,
        product_name=product_name,
        day=day,
        period_avg=period_avg,
        period_median=period_median,
        z_scores=z_scores,
        factors=factors,
        summary=summary,
    )
