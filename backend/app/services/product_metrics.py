"""
45 метрик «Статистики товара» — реестр + агрегации.

Каждая метрика имеет:
- key: внутренний id
- label: для UI
- description: tooltip
- group: «Трафик» / «Заказы» / «Цена» / «Реклама» / «Прогноз» / «Остатки»
- source: api / model / derived / xlsx
- format: number / currency / percent
- agg: sum / avg / weighted / last / first — как сворачивать в недели/месяцы

Sum: складываем (показы, клики, заказы, выручка).
Avg: простое среднее по дням (CTR — не корректно для сложений, но для weekly
  rollup точнее — weighted by impressions, см. agg='weighted').
Last: последнее значение за окно (для остатков).
Weighted: взвешенное среднее (например, цена покупателя — на qty).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


AggType = Literal["sum", "avg", "weighted_by", "last", "first"]
Format = Literal["number", "currency", "percent", "days"]


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    group: str
    description: str
    source: str  # api/model/derived/xlsx/manual
    format: Format
    agg: AggType
    weight_by: str | None = None  # для weighted_by: на что взвешиваем


# === Полный каталог 45 метрик ===
METRICS: list[Metric] = [
    # ---- Трафик и воронка ----
    Metric("impressions",         "Показы",              "Трафик",
           "Общая метрика «Показы» = карточка в выдаче (analytics_daily.hits_view). "
           "Совпадает с Ozon UI Аналитика → Показы (≈4× от search+pdp разбивки).",
           "api", "number", "sum"),
    Metric("impressions_legacy",  "Просмотры карточки",  "Трафик",
           "hits_view_search + hits_view_pdp — пользователь посмотрел карточку. "
           "Подмножество «Показов» (только после клика на карточку).",
           "api", "number", "sum"),
    Metric("ad_impressions",      "Рекламные показы",    "Трафик",
           "ad_statistics.impressions — реклама показала карточку.",
           "api", "number", "sum"),
    Metric("ad_imp_share",        "Доля рекл. показов",  "Трафик",
           "ad_impressions / impressions × 100%.",
           "derived", "percent", "weighted_by", "impressions"),
    Metric("imp_search",          "Показы в поиске и каталоге", "Трафик",
           "hits_view_search — карточка попала в поисковую выдачу/каталог. "
           "Совпадает с одноимённой метрикой Ozon UI Excel.",
           "api", "number", "sum"),
    Metric("ad_imp_search",       "Рекл. показы в поиске", "Трафик",
           "Рекламные показы в поиске (если разбито по типам).",
           "api", "number", "sum"),
    Metric("imp_pdp",             "Посещения карточки",  "Трафик",
           "hits_view_pdp — пользователь зашёл на страницу товара (PDP). "
           "Совпадает с Ozon UI Excel «Посещения карточки».",
           "api", "number", "sum"),
    Metric("position_search",     "Позиция в поиске",    "Трафик",
           "Средняя позиция в выдаче за день (analytics_daily.position_category).",
           "api", "number", "weighted_by", "impressions"),
    Metric("clicks",              "Клики",               "Трафик",
           "Σ кликов (CTR × impressions × cabinet aggregate).",
           "api", "number", "sum"),
    Metric("ad_clicks",           "Клики рекламные",     "Трафик",
           "Клики из ad_statistics.",
           "api", "number", "sum"),
    Metric("organic_clicks",      "Клики органические",  "Трафик",
           "Общие клики − рекламные.",
           "derived", "number", "sum"),
    Metric("ctr",                 "CTR, %",              "Трафик",
           "clicks / impressions × 100%. Взвешенно по показам в роллапе.",
           "derived", "percent", "weighted_by", "impressions"),
    Metric("ad_traffic_share",    "Доля рекл. трафика",  "Трафик",
           "ad_clicks / clicks × 100%.",
           "derived", "percent", "weighted_by", "clicks"),
    Metric("cart_count",          "В корзину",           "Трафик",
           "hits_tocart_search + hits_tocart_pdp.",
           "api", "number", "sum"),
    Metric("ad_carts",            "Рекл. корзины",       "Трафик",
           "Корзины из рекламы (если есть в ad_statistics).",
           "api", "number", "sum"),
    Metric("conv_click_to_cart",  "Конверсия клик→корзина", "Трафик",
           "cart_count / clicks × 100%.",
           "derived", "percent", "weighted_by", "clicks"),
    Metric("conv_cart_to_order",  "Конверсия корзина→заказ", "Трафик",
           "orders / cart_count × 100%.",
           "derived", "percent", "weighted_by", "cart_count"),
    Metric("conv_click_to_order", "Конверсия клик→заказ", "Трафик",
           "orders / clicks × 100%.",
           "derived", "percent", "weighted_by", "clicks"),

    # ---- Заказы и продажи ----
    Metric("revenue",             "Сумма заказов (по цене продавца), ₽", "Заказы",
           "Σ price × qty за день по order_items. ВСЕ статусы (включая в пути, "
           "отмены). Это НЕ выручка продавца — берётся цена ДО фактической "
           "доставки, без Баллов и Программ партнёров. Для P&L и налога "
           "использовать seller_revenue.",
           "api", "currency", "sum"),
    Metric("seller_revenue",      "Выручка продавца, ₽", "Заказы",
           "Σ accruals_for_sale из transactions (OperationAgentDeliveredToCustomer): "
           "что Ozon РЕАЛЬНО начислил продавцу = Выручка + Баллы за скидки + "
           "Программы партнёров. Только по доставленным заказам, по operation_date. "
           "База маржи и налога. Источник истины P&L.",
           "api", "currency", "sum"),
    Metric("orders",              "Заказы (шт)",         "Заказы",
           "Сколько заказов за день.",
           "api", "number", "sum"),
    Metric("ad_orders",           "Заказы рекламные",    "Заказы",
           "Заказы из ad_statistics.orders.",
           "api", "number", "sum"),
    Metric("cpo",                 "CPO, ₽",              "Заказы",
           "ad_spend / ad_orders — цена одного рекл. заказа.",
           "derived", "currency", "weighted_by", "ad_orders"),
    Metric("delivered",           "Выкупили (шт)",       "Заказы",
           "Заказы со статусом delivered.",
           "api", "number", "sum"),
    Metric("returned_after",      "Вернули после выкупа", "Заказы",
           "returns с return_date в окне.",
           "api", "number", "sum"),
    Metric("cancelled",           "Отменили (шт)",       "Заказы",
           "Заказы со статусом cancelled.",
           "api", "number", "sum"),
    Metric("pending_decision",    "Ждут решения",        "Заказы",
           "Заказы в статусе in_process / delivering.",
           "api", "number", "last"),
    Metric("buyout_rate",         "Выкупаемость, %",     "Заказы",
           "delivered / orders × 100%.",
           "derived", "percent", "weighted_by", "orders"),

    # ---- Цена ----
    Metric("seller_price",        "Цена продавца до СПП, ₽", "Цена",
           "Σ price × qty / Σ qty — что Ozon начислил продавцу. База маржи.",
           "api", "currency", "weighted_by", "delivered"),
    Metric("customer_price",      "Цена покупателя (с СПП), ₽", "Цена",
           "Σ customer_price × qty / Σ qty — что реально платил покупатель.",
           "api", "currency", "weighted_by", "delivered"),
    Metric("spp_pct",             "% скидки МП (СПП)",   "Цена",
           "(seller − customer) / seller × 100%.",
           "derived", "percent", "weighted_by", "delivered"),

    # ---- Реклама ----
    Metric("ad_spend",            "Расход на рекламу, ₽", "Реклама",
           "Σ spend из ad_statistics.",
           "api", "currency", "sum"),
    Metric("drr",                 "ДРР, %",              "Реклама",
           "ad_spend / revenue × 100% — доля рекламы в выручке.",
           "derived", "percent", "weighted_by", "revenue"),
    Metric("cps",                 "CPS, ₽",              "Реклама",
           "ad_spend / orders — стоимость одной продажи.",
           "derived", "currency", "weighted_by", "orders"),

    # ---- Прогноз (модельные оценки) ----
    Metric("forecast_units",      "Прогноз продаж, шт",  "Прогноз",
           "Предсказание из sales_velocity_cache. Помечен 'оценка'.",
           "model", "number", "sum"),
    Metric("forecast_revenue",    "Прогноз выручки, ₽",  "Прогноз",
           "forecast_units × avg_price.",
           "model", "currency", "sum"),
    Metric("forecast_cogs",       "Прогноз себес проданных, ₽", "Прогноз",
           "forecast_units × cost_per_unit.",
           "model", "currency", "sum"),
    Metric("forecast_mp_costs",   "Прогноз расходов МП, ₽", "Прогноз",
           "Прогноз комиссий/логистики/эквайринга на forecast_units.",
           "model", "currency", "sum"),
    Metric("forecast_net_profit", "Прогноз чистой прибыли, ₽", "Прогноз",
           "Прогноз = forecast_revenue − cogs − mp_costs − налог.",
           "model", "currency", "sum"),
    Metric("forecast_net_per_unit", "Прогноз прибыли на ед, ₽", "Прогноз",
           "forecast_net_profit / forecast_units.",
           "model", "currency", "weighted_by", "forecast_units"),

    # ---- Семантика (Premium Plus /v1/analytics/product-queries) ----
    Metric("unique_search_users", "Уник. пользователей из поиска", "Семантика",
           "Сколько уникальных юзеров видели карточку в поиске Ozon.",
           "api", "number", "sum"),
    Metric("unique_view_users",   "Уник. посетителей карточки",   "Семантика",
           "Уникальные юзеры открыли карточку.",
           "api", "number", "sum"),
    Metric("search_position",     "Позиция в поиске",             "Семантика",
           "Средняя позиция товара в поиске.",
           "api", "number", "weighted_by", "unique_search_users"),
    Metric("search_view_conversion", "Конверсия поиск→карточка, %", "Семантика",
           "Из видевших в поиске — сколько % открыли карточку.",
           "api", "percent", "weighted_by", "unique_search_users"),
    Metric("search_gmv",          "Выручка с поиска, ₽",          "Семантика",
           "GMV от пользователей из поисковой выдачи.",
           "api", "currency", "sum"),

    # ---- Реализация (Premium Plus /v1/finance/realization/by-day) ----
    Metric("realization_qty",     "Реализация шт (точно)",        "Реализация",
           "Точное qty продано (отчёт Ozon, не агрегат).",
           "api", "number", "sum"),
    Metric("realization_avg_cp",  "Цена покупателя (точно)",      "Реализация",
           "Точная weighted_avg customer_price из realization/by-day.",
           "api", "currency", "weighted_by", "realization_qty"),
    Metric("realization_bonus",   "СПП-компенсация Ozon",         "Реализация",
           "Bonus от Ozon продавцу за СПП-скидки.",
           "api", "currency", "sum"),
    Metric("realization_fee",     "Комиссия Ozon (точно)",        "Реализация",
           "Точная комиссия Ozon из realization/by-day.",
           "api", "currency", "sum"),

    # ---- Остатки ----
    Metric("stock_warehouse",     "Остаток на складе",   "Остатки",
           "Σ free_to_sell по всем складам — на конец дня (last).",
           "api", "number", "last"),
    Metric("in_transit_to",       "В пути к клиенту",    "Остатки",
           "Σ in_transit (доставка).",
           "api", "number", "last"),
    Metric("in_transit_back",     "В пути от клиента",   "Остатки",
           "Возвраты в пути.",
           "api", "number", "last"),
    Metric("stock_total",         "Суммарный остаток",   "Остатки",
           "free_to_sell + in_transit_to + reserved.",
           "derived", "number", "last"),
    Metric("turnover_days",       "Оборот товара, дней", "Остатки",
           "stock_total / avg_daily_delivered.",
           "derived", "days", "last"),
    Metric("days_left",           "Хватит на, дней",     "Остатки",
           "stock_total / forecast_daily_units. Сколько дней до stockout.",
           "model", "days", "last"),
    Metric("stock_cogs",          "Себестоимость остатков, ₽", "Остатки",
           "stock_total × cost_per_unit.",
           "derived", "currency", "last"),
]


METRICS_BY_KEY = {m.key: m for m in METRICS}
METRIC_GROUPS = ["Трафик", "Заказы", "Цена", "Реклама",
                 "Семантика", "Реализация", "Прогноз", "Остатки"]


def aggregate_bucket(metric: Metric, daily_rows: list[dict]) -> float | None:
    """Свернуть дневные значения метрики в один (для недели/месяца/всего периода).

    daily_rows: [{'value': X, 'weight': Y}, ...]
    Для weighted_by — weight уже посчитан вызывающей стороной (вес метрики).
    """
    vals = [r["value"] for r in daily_rows if r.get("value") is not None]
    if not vals:
        return None
    if metric.agg == "sum":
        return sum(vals)
    if metric.agg == "last":
        return next((r["value"] for r in reversed(daily_rows)
                     if r.get("value") is not None), None)
    if metric.agg == "first":
        return next((r["value"] for r in daily_rows if r.get("value") is not None), None)
    if metric.agg == "avg":
        return sum(vals) / len(vals)
    if metric.agg == "weighted_by":
        num = sum((r.get("value") or 0) * (r.get("weight") or 0) for r in daily_rows)
        den = sum((r.get("weight") or 0) for r in daily_rows)
        return num / den if den else None
    return None
