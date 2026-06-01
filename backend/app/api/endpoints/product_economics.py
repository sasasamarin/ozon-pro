"""
«Экономика продаж» — единая P&L-таблица по товарам (nepsell-канон).

Колонки на единицу + итог за период:
- qty_delivered (выкупленные единицы)
- avg_seller_price (≈ accruals_for_sale — выручка продавца за единицу)
- avg_customer_price (≈ что физически платил покупатель с СПП)
- cost_per_unit (себестоимость закупки)
- commission_per_unit (Ozon-комиссия % × seller_price)
- logistics_per_unit (~306 ₽ — delivery + last_mile)
- acquiring_per_unit (1.5% от seller_price)
- ad_spend_per_unit (AdStatistics.spend / qty)
- operating_profit (выручка − все вычеты)
- tax (по компании-режиму через services/tax.py)
- net_profit (после налога) и net_margin %

GET /api/v1/products/economics?days=30&product_id=...&cabinet_ids=...
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.product_filter import build_product_filter_sql, category_descendants
from app.db.session import get_db
from app.models import Company, OzonAccount, Product, User
from app.services.finance_consts import (
    ACQUIRING_PCT,
    DEFAULT_COMMISSION_PCT,
    LOGISTICS_PER_UNIT,
    calc_acquiring,
    calc_logistics,
    get_commission_pct,
)
from app.services.tax import calc_tax

router = APIRouter()
UTC = timezone.utc


class EconomicsRow(BaseModel):
    product_id: str
    product_name: str
    offer_id: str
    ozon_sku: int
    cabinet_name: str
    is_archived: bool

    # Source-флаги для прозрачности: какое поле откуда пришло.
    # Значения: 'api' (живые данные Ozon API) / 'xlsx' (точный отчёт)
    #         / 'estimated' (оценка по эвристикам) / 'manual' (ручной ввод)
    # Ключи — те же что у полей ниже, например {"storage_total": "xlsx", ...}.
    sources: dict[str, str] = {}

    qty_delivered: int
    revenue: float                 # brut — sales API (oi.price × qty)
    returned_revenue: float
    effective_revenue: float

    # Доплаты Ozon (только если XLSX, иначе 0)
    spp_points: float
    partner_programs: float

    # На единицу
    avg_seller_price: float | None
    avg_customer_price: float | None
    spp_pct: float | None

    cost_per_unit: float | None
    commission_pct: float
    commission_per_unit: float
    logistics_per_unit: float
    acquiring_per_unit: float
    ad_spend_per_unit: float

    # Итоги за период (× qty)
    cost_total: float
    commission_total: float
    logistics_total: float
    last_mile_total: float
    storage_total: float
    posting_handling_total: float
    acquiring_total: float
    return_handling_total: float
    reverse_logistics_total: float
    disposal_total: float
    ovh_extra_total: float
    operational_errors_total: float
    ad_cpc_total: float
    ad_cpo_total: float
    ad_star_total: float
    ad_paid_brand_total: float
    ad_reviews_total: float
    ad_spend_total: float           # суммарная реклама (API live или sum из XLSX)

    operating_profit: float
    operating_margin_pct: float | None

    tax_amount: float
    vat_amount: float
    net_profit: float
    net_margin_pct: float | None

    cost_missing: bool

    # Сверка XLSX (если был файл)
    ozon_profit: float | None
    ozon_profit_diff: float | None


class EconomicsTotals(BaseModel):
    qty_delivered: int
    revenue: float
    returned_revenue: float
    effective_revenue: float
    cost_total: float
    commission_total: float
    logistics_total: float
    acquiring_total: float
    ad_spend_total: float
    storage_total: float                  # из XLSX когда загружен
    operating_profit: float
    tax_amount: float
    vat_amount: float
    net_profit: float
    net_margin_pct: float | None
    products_total: int
    products_with_cost: int
    products_missing_cost: int
    # Сколько товаров получили точные числа из XLSX vs оценку
    products_with_xlsx: int
    products_estimated: int


class EconomicsResp(BaseModel):
    period_from: str
    period_to: str
    tax_regime: str
    tax_regime_label: str
    tax_rate_pct: float
    # Информация о покрытии XLSX за этот период
    months_with_xlsx: list[str]           # ["2026-05-01"] если есть монти за период
    xlsx_coverage_pct: float              # % товаров с точными числами из XLSX
    rows: list[EconomicsRow]
    totals: EconomicsTotals


@router.get("/", response_model=EconomicsResp)
async def get_economics(
    days: int = Query(30, ge=1, le=365),
    date_from: date_cls | None = Query(None),
    date_to: date_cls | None = Query(None),
    cabinet_ids: list[uuid.UUID] | None = Query(None),
    product_id: uuid.UUID | None = Query(None),
    category_id: int | None = Query(None, description="Категория из Topbar (включая потомков)"),
    tags: list[str] | None = Query(None, description="Фильтр по тегам (OR-логика)"),
    include_archived: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EconomicsResp:
    # Период
    today = datetime.now(UTC).date()
    if not date_to:
        date_to = today
    if not date_from:
        date_from = date_to - timedelta(days=days)

    # Налог компании
    company = (await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )).scalar_one()
    tax_regime = company.tax_regime or "usn_income"
    tax_rate = float(company.tax_rate_pct or 6.0)
    vat_rate = float(company.vat_rate_pct) if company.vat_rate_pct else None

    # Список разрешённых кабинетов
    cab_q = select(OzonAccount.id, OzonAccount.name).where(
        OzonAccount.company_id == current_user.company_id,
        OzonAccount.deleted_at.is_(None),
    )
    if cabinet_ids:
        cab_q = cab_q.where(OzonAccount.id.in_(cabinet_ids))
    cab_rows = (await db.execute(cab_q)).all()
    if not cab_rows:
        return EconomicsResp(
            period_from=date_from.isoformat(), period_to=date_to.isoformat(),
            tax_regime=tax_regime, tax_regime_label=tax_regime.upper(),
            tax_rate_pct=tax_rate,
            months_with_xlsx=[], xlsx_coverage_pct=0.0,
            rows=[], totals=_empty_totals(),
        )
    allowed_acc_ids = [r[0] for r in cab_rows]
    acc_name_map = {r[0]: r[1] for r in cab_rows}

    # Per-product агрегация заказов за период (только доставленные)
    where_extra = ""
    params: dict = {
        "accs": [str(x) for x in allowed_acc_ids],
        "df": date_from, "dt": date_to,
    }
    if product_id is not None:
        where_extra = "AND oi.product_id = :pid"
        params["pid"] = str(product_id)
    if not include_archived:
        where_extra += " AND p.is_archived = false"

    # Глобальные фильтры из Topbar (category_id + tags)
    desc_ids: list[int] | None = None
    if category_id is not None:
        desc_ids = await category_descendants(db, category_id=category_id)
    filter_sql, filter_params = build_product_filter_sql(
        category_ids=desc_ids, tags=tags, p_alias="p",
    )
    where_extra += " " + filter_sql
    params.update(filter_params)

    sql = f"""
        SELECT
            p.id::text AS product_id,
            p.name, p.offer_id, p.ozon_sku, p.is_archived,
            p.ozon_account_id::text AS account_id,
            p.cost_price::float                AS cost_price,
            p.sales_percent_fbo::float         AS comm_pct,
            p.acquiring_amount::float          AS prod_acq_amount,
            COUNT(*)                            AS qty_delivered,
            SUM(oi.price)::float                AS revenue,
            AVG(oi.price)::float                AS avg_seller_price,
            AVG(oi.customer_price)::float       AS avg_customer_price
        FROM order_items oi
        JOIN orders o   ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        WHERE o.ozon_account_id = ANY(:accs)
          AND o.order_created_at >= :df
          AND o.order_created_at < (CAST(:dt AS date) + interval '1 day')
          AND o.status = 'delivered'
          AND oi.price > 0
          {where_extra}
        GROUP BY p.id, p.name, p.offer_id, p.ozon_sku, p.is_archived,
                 p.ozon_account_id, p.cost_price, p.sales_percent_fbo
        ORDER BY revenue DESC NULLS LAST
    """
    rows = (await db.execute(text(sql), params)).all()

    # ad_spend per-product:
    # ad_statistics хранит per-campaign-per-day (product_id=NIL_UUID placeholder),
    # сами товары per-кампания не синкаются в ad_campaign_products. Значит
    # точного per-SKU из API сейчас НЕТ.
    # Решение: распределяем общий ad_spend per-cabinet пропорционально revenue
    # доставленных товаров за тот же период. Это оценка (source='estimated')
    # для месяцев без XLSX. Если XLSX загружен — он override это точными
    # цифрами (ad_cpc + ad_cpo + ad_star + ad_paid_brand + ad_reviews per-SKU).
    ad_cabinet_rows = (await db.execute(text("""
        SELECT ozon_account_id::text AS acc, SUM(spend)::float AS total_spend
        FROM ad_statistics
        WHERE ozon_account_id = ANY(CAST(:accs AS uuid[]))
          AND date >= :df AND date <= :dt
        GROUP BY ozon_account_id
    """), {"accs": params["accs"], "df": date_from, "dt": date_to})).all()
    ad_total_by_cab: dict[str, float] = {r.acc: float(r.total_spend or 0) for r in ad_cabinet_rows}

    # Revenue per-cabinet за период — база для пропорции
    rev_cab_rows = (await db.execute(text("""
        SELECT p.ozon_account_id::text AS acc, SUM(oi.price)::float AS rev
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        WHERE p.ozon_account_id = ANY(CAST(:accs AS uuid[]))
          AND o.status = 'delivered'
          AND o.order_created_at >= :df
          AND o.order_created_at < (CAST(:dt AS date) + interval '1 day')
        GROUP BY p.ozon_account_id
    """), {"accs": params["accs"], "df": date_from, "dt": date_to})).all()
    rev_total_by_cab: dict[str, float] = {r.acc: float(r.rev or 0) for r in rev_cab_rows}

    # ad_by_prod[product_id] = пропорциональное распределение
    ad_by_prod: dict[str, float] = {}  # будем считать ниже per-row

    # returns per-product за тот же период (по return_date — «зеркало Ozon»)
    ret_rows = (await db.execute(text("""
        SELECT product_id::text pid, COALESCE(SUM(return_amount), 0)::float ret_sum
        FROM returns
        WHERE ozon_account_id = ANY(:accs)
          AND return_date >= :df
          AND return_date < (CAST(:dt AS date) + interval '1 day')
        GROUP BY product_id
    """), {"accs": params["accs"], "df": date_from, "dt": date_to})).all()
    ret_by_prod: dict[str, float] = {r.pid: float(r.ret_sum or 0) for r in ret_rows}

    # === MONTHLY UNIT ECONOMY: точные XLSX-числа из «Экономика магазина» ===
    # Если за период есть загруженный отчёт Ozon — берём расходы оттуда per-SKU.
    # Иначе остаётся текущая модель оценок. Матчим по ozon_sku (sku в файле).
    # Период XLSX = month (первый день). За period_from..period_to берём ВСЕ
    # месяцы которые пересекаются и суммируем по SKU.
    xlsx_rows = (await db.execute(text("""
        SELECT
          ue.cabinet_id::text AS cab_id,
          ue.sku,
          ue.month::text AS month_iso,
          SUM(COALESCE(ue.revenue, 0))::float AS xrevenue,
          SUM(COALESCE(ue.spp_points, 0))::float AS xspp,
          SUM(COALESCE(ue.partner_programs, 0))::float AS xpartner,
          SUM(COALESCE(ue.ozon_commission, 0))::float AS xcomm,
          SUM(COALESCE(ue.acquiring, 0))::float AS xacq,
          SUM(COALESCE(ue.posting_handling, 0))::float AS xposting,
          SUM(COALESCE(ue.logistics, 0))::float AS xlog,
          SUM(COALESCE(ue.last_mile, 0))::float AS xlast,
          SUM(COALESCE(ue.storage, 0))::float AS xstorage,
          SUM(COALESCE(ue.return_handling, 0))::float AS xrethnd,
          SUM(COALESCE(ue.reverse_logistics, 0))::float AS xrevlog,
          SUM(COALESCE(ue.disposal, 0))::float AS xdisp,
          SUM(COALESCE(ue.ovh_extra, 0))::float AS xovh,
          SUM(COALESCE(ue.operational_errors, 0))::float AS xopserr,
          SUM(COALESCE(ue.ad_cpc, 0))::float AS xcpc,
          SUM(COALESCE(ue.ad_cpo, 0))::float AS xcpo,
          SUM(COALESCE(ue.ad_star, 0))::float AS xstar,
          SUM(COALESCE(ue.ad_paid_brand, 0))::float AS xbrand,
          SUM(COALESCE(ue.ad_reviews, 0))::float AS xreviews,
          SUM(COALESCE(ue.ozon_profit, 0))::float AS xprofit,
          SUM(COALESCE(ue.delivered_qty, 0))::int AS xdelivered,
          SUM(COALESCE(ue.returned_qty, 0))::int AS xreturned
        FROM monthly_unit_economy ue
        WHERE ue.cabinet_id = ANY(CAST(:accs AS uuid[]))
          AND ue.month >= date_trunc('month', CAST(:df AS date))
          AND ue.month <= date_trunc('month', CAST(:dt AS date))
        GROUP BY ue.cabinet_id, ue.sku, ue.month
    """), {"accs": params["accs"], "df": date_from, "dt": date_to})).all()
    # Ключ = (cabinet_id, ozon_sku) → суммируем по месяцам если их несколько
    xlsx_by_sku: dict[tuple[str, int], dict] = {}
    months_covered: set[str] = set()
    for x in xlsx_rows:
        key = (x.cab_id, int(x.sku))
        months_covered.add(x.month_iso[:10])
        if key in xlsx_by_sku:
            # суммируем если за период попало несколько месяцев
            prev = xlsx_by_sku[key]
            for k in ("xrevenue", "xspp", "xpartner", "xcomm", "xacq", "xposting",
                      "xlog", "xlast", "xstorage", "xrethnd", "xrevlog", "xdisp",
                      "xovh", "xopserr", "xcpc", "xcpo", "xstar", "xbrand", "xreviews",
                      "xprofit", "xdelivered", "xreturned"):
                prev[k] = (prev.get(k, 0) or 0) + (getattr(x, k) or 0)
        else:
            xlsx_by_sku[key] = {
                "xrevenue": x.xrevenue, "xspp": x.xspp, "xpartner": x.xpartner,
                "xcomm": x.xcomm, "xacq": x.xacq, "xposting": x.xposting,
                "xlog": x.xlog, "xlast": x.xlast, "xstorage": x.xstorage,
                "xrethnd": x.xrethnd, "xrevlog": x.xrevlog, "xdisp": x.xdisp,
                "xovh": x.xovh, "xopserr": x.xopserr,
                "xcpc": x.xcpc, "xcpo": x.xcpo, "xstar": x.xstar,
                "xbrand": x.xbrand, "xreviews": x.xreviews,
                "xprofit": x.xprofit, "xdelivered": x.xdelivered, "xreturned": x.xreturned,
            }

    # Построение строк
    out_rows: list[EconomicsRow] = []
    tot_qty = 0
    tot_revenue = tot_returned = tot_eff_rev = 0.0
    tot_cost = tot_comm = tot_log = tot_acq = tot_ad = 0.0
    tot_storage = 0.0
    tot_op = tot_tax = tot_vat = tot_net = 0.0
    p_with_cost = 0
    p_with_xlsx = 0

    for r in rows:
        qty = int(r.qty_delivered or 0)
        revenue = float(r.revenue or 0)
        if qty == 0 or revenue == 0:
            continue

        avg_seller = float(r.avg_seller_price) if r.avg_seller_price else None
        avg_customer = float(r.avg_customer_price) if r.avg_customer_price else None
        spp_pct = None
        if avg_seller and avg_customer and avg_seller > 0 and avg_customer < avg_seller:
            spp_pct = round((1 - avg_customer / avg_seller) * 100, 1)

        cost_per = float(r.cost_price) if r.cost_price else None
        commission_pct = get_commission_pct(product_sales_percent_fbo=r.comm_pct)
        prod_acq_amount = float(r.prod_acq_amount) if r.prod_acq_amount else None

        # === STEP 1: BASELINE из API live данных + текущих оценок ===
        # Эти числа доступны всегда (API синкается каждый час).
        # Source-флаги собираем по ходу.
        sources: dict[str, str] = {
            "revenue": "api",          # из order_items.price (накопления продаж)
            "returned_revenue": "api", # из returns
            "qty_delivered": "api",    # из order_items
            "cost_total": "manual" if cost_per else "missing",
        }
        # Комиссия — оценка через products.sales_percent_fbo или fallback
        comm_per = (avg_seller or 0) * commission_pct / 100
        comm_total = comm_per * qty
        sources["commission_total"] = "estimated"
        # Эквайринг — если есть Product.acquiring_amount из API → точное; иначе оценка
        acq_calc = calc_acquiring(
            seller_price=avg_seller or 0, qty=qty,
            product_acquiring_amount=prod_acq_amount,
        )
        acq_total = acq_calc.amount
        acq_per = acq_total / qty if qty else 0.0
        sources["acquiring_total"] = "api" if acq_calc.source == "api" else "estimated"
        # Логистика — пока оценка 306×qty (real_amount из Transaction добавим позже)
        log_calc = calc_logistics(qty=qty)
        log_total = log_calc.amount
        sources["logistics_total"] = "estimated"
        # Реклама общая — пропорция от cabinet ad_spend × (revenue_product/revenue_cabinet)
        # Пометка 'estimated' — это не точно per-SKU из API (Ozon Perf API такого не отдаёт),
        # а распределение по доле выручки. XLSX перекроет точными числами если есть.
        cab_ad = ad_total_by_cab.get(r.account_id, 0.0)
        cab_rev = rev_total_by_cab.get(r.account_id, 0.0)
        ad_total = (revenue / cab_rev * cab_ad) if cab_rev > 0 else 0.0
        ad_per = ad_total / qty if qty else 0.0
        sources["ad_spend_total"] = "estimated"
        # Поля только из XLSX — по умолчанию 0
        storage_total = 0.0
        last_mile_total = 0.0
        posting_handling_total = 0.0
        return_handling_total = 0.0
        reverse_logistics_total = 0.0
        disposal_total = 0.0
        ovh_extra_total = 0.0
        operational_errors_total = 0.0
        ad_cpc_total = ad_cpo_total = ad_star_total = 0.0
        ad_paid_brand_total = ad_reviews_total = 0.0
        spp_points = 0.0
        partner_programs = 0.0
        ozon_profit_x: float | None = None

        # === STEP 2: XLSX OVERRIDE — точечно перекрываем то что Ozon отдал в файле ===
        # API остаётся источником для revenue/qty/returns/ad_total — это live.
        # XLSX даёт ТОЧНЫЕ числа для расходов которые API per-SKU не отдаёт.
        xlsx = xlsx_by_sku.get((r.account_id, int(r.ozon_sku)))
        if xlsx:
            p_with_xlsx += 1
            # Доплаты Ozon: spp_points + partner_programs (только в XLSX)
            spp_points = float(xlsx["xspp"] or 0)
            partner_programs = float(xlsx["xpartner"] or 0)
            sources["spp_points"] = "xlsx"
            sources["partner_programs"] = "xlsx"
            # Точные расходы из файла (override оценок)
            if xlsx["xcomm"]:
                comm_total = abs(float(xlsx["xcomm"]))
                comm_per = comm_total / qty if qty else 0
                sources["commission_total"] = "xlsx"
            if xlsx["xacq"]:
                acq_total = abs(float(xlsx["xacq"]))
                acq_per = acq_total / qty if qty else 0
                sources["acquiring_total"] = "xlsx"
            if xlsx["xlog"]:
                log_total = abs(float(xlsx["xlog"]))
                sources["logistics_total"] = "xlsx"
            # Поля доступные ТОЛЬКО из XLSX (API не отдаёт per-SKU)
            last_mile_total = abs(float(xlsx["xlast"] or 0))
            storage_total = abs(float(xlsx["xstorage"] or 0))
            posting_handling_total = abs(float(xlsx["xposting"] or 0))
            return_handling_total = abs(float(xlsx["xrethnd"] or 0))
            reverse_logistics_total = abs(float(xlsx["xrevlog"] or 0))
            disposal_total = abs(float(xlsx["xdisp"] or 0))
            ovh_extra_total = abs(float(xlsx["xovh"] or 0))
            operational_errors_total = abs(float(xlsx["xopserr"] or 0))
            for f in ("last_mile_total", "storage_total", "posting_handling_total",
                      "return_handling_total", "reverse_logistics_total",
                      "disposal_total", "ovh_extra_total", "operational_errors_total"):
                sources[f] = "xlsx"
            # Реклама детально из XLSX — override общий ad_total суммой по типам
            ad_cpc_total = abs(float(xlsx["xcpc"] or 0))
            ad_cpo_total = abs(float(xlsx["xcpo"] or 0))
            ad_star_total = abs(float(xlsx["xstar"] or 0))
            ad_paid_brand_total = abs(float(xlsx["xbrand"] or 0))
            ad_reviews_total = abs(float(xlsx["xreviews"] or 0))
            ad_total_xlsx = (ad_cpc_total + ad_cpo_total + ad_star_total
                             + ad_paid_brand_total + ad_reviews_total)
            if ad_total_xlsx > 0:
                ad_total = ad_total_xlsx
                ad_per = ad_total / qty if qty else 0
                sources["ad_spend_total"] = "xlsx"
            ozon_profit_x = float(xlsx["xprofit"] or 0) if xlsx["xprofit"] else None

        cost_total = (cost_per * qty) if cost_per else 0.0
        returned_revenue = ret_by_prod.get(r.product_id, 0.0)

        # Эффективная выручка: с XLSX добавляем компенсацию СПП,
        # без — просто revenue минус возвраты.
        if xlsx:
            effective_revenue = revenue + spp_points + partner_programs - returned_revenue
        else:
            effective_revenue = revenue - returned_revenue

        # op_profit = effective_revenue − все расходы Ozon − реклама − cost
        # Не двойной учёт: comm_total / log_total / acq_total суммируют все
        # отдельные статьи если XLSX, иначе только базовая модель.
        all_ozon_expenses = (
            comm_total + acq_total + posting_handling_total + log_total + last_mile_total
            + storage_total + return_handling_total + reverse_logistics_total
            + disposal_total + ovh_extra_total + operational_errors_total
        )
        op_profit = effective_revenue - cost_total - all_ozon_expenses - ad_total
        tax_res = calc_tax(
            revenue=effective_revenue, gross_profit=op_profit,
            tax_regime=tax_regime, tax_rate_pct=tax_rate, vat_rate_pct=vat_rate,
        )

        net = tax_res.net_profit
        net_margin = (net / revenue * 100) if revenue else None
        op_margin = (op_profit / revenue * 100) if revenue else None

        # Сверка XLSX: наш op_profit (БЕЗ себестоимости) должен ≈ ozon_profit
        ozon_diff = None
        if ozon_profit_x is not None:
            our_no_cogs = op_profit + cost_total
            ozon_diff = round(abs(our_no_cogs - ozon_profit_x), 2)

        out_rows.append(EconomicsRow(
            product_id=r.product_id,
            product_name=r.name,
            offer_id=r.offer_id,
            ozon_sku=r.ozon_sku,
            cabinet_name=acc_name_map.get(uuid.UUID(r.account_id), "—"),
            is_archived=bool(r.is_archived),
            sources=sources,
            qty_delivered=qty,
            revenue=round(revenue, 2),
            returned_revenue=round(returned_revenue, 2),
            effective_revenue=round(effective_revenue, 2),
            spp_points=round(spp_points, 2),
            partner_programs=round(partner_programs, 2),
            avg_seller_price=round(avg_seller, 2) if avg_seller else None,
            avg_customer_price=round(avg_customer, 2) if avg_customer else None,
            spp_pct=spp_pct,
            cost_per_unit=cost_per,
            commission_pct=round(commission_pct, 2),
            commission_per_unit=round(comm_per, 2),
            logistics_per_unit=LOGISTICS_PER_UNIT,
            acquiring_per_unit=round(acq_per, 2),
            ad_spend_per_unit=round(ad_per, 2),
            cost_total=round(cost_total, 2),
            commission_total=round(comm_total, 2),
            logistics_total=round(log_total, 2),
            last_mile_total=round(last_mile_total, 2),
            storage_total=round(storage_total, 2),
            posting_handling_total=round(posting_handling_total, 2),
            acquiring_total=round(acq_total, 2),
            return_handling_total=round(return_handling_total, 2),
            reverse_logistics_total=round(reverse_logistics_total, 2),
            disposal_total=round(disposal_total, 2),
            ovh_extra_total=round(ovh_extra_total, 2),
            operational_errors_total=round(operational_errors_total, 2),
            ad_cpc_total=round(ad_cpc_total, 2),
            ad_cpo_total=round(ad_cpo_total, 2),
            ad_star_total=round(ad_star_total, 2),
            ad_paid_brand_total=round(ad_paid_brand_total, 2),
            ad_reviews_total=round(ad_reviews_total, 2),
            ad_spend_total=round(ad_total, 2),
            operating_profit=round(op_profit, 2),
            operating_margin_pct=round(op_margin, 2) if op_margin is not None else None,
            tax_amount=tax_res.tax_amount,
            vat_amount=tax_res.vat_amount,
            net_profit=net,
            net_margin_pct=round(net_margin, 2) if net_margin is not None else None,
            cost_missing=cost_per is None,
            ozon_profit=round(ozon_profit_x, 2) if ozon_profit_x is not None else None,
            ozon_profit_diff=ozon_diff,
        ))

        tot_qty += qty
        tot_revenue += revenue
        tot_returned += returned_revenue
        tot_eff_rev += effective_revenue
        tot_cost += cost_total
        tot_comm += comm_total
        tot_log += log_total
        tot_acq += acq_total
        tot_ad += ad_total
        tot_storage += storage_total
        tot_op += op_profit
        tot_tax += tax_res.tax_amount
        tot_vat += tax_res.vat_amount
        tot_net += net
        if cost_per is not None:
            p_with_cost += 1

    totals = EconomicsTotals(
        qty_delivered=tot_qty,
        revenue=round(tot_revenue, 2),
        returned_revenue=round(tot_returned, 2),
        effective_revenue=round(tot_eff_rev, 2),
        cost_total=round(tot_cost, 2),
        commission_total=round(tot_comm, 2),
        logistics_total=round(tot_log, 2),
        acquiring_total=round(tot_acq, 2),
        ad_spend_total=round(tot_ad, 2),
        storage_total=round(tot_storage, 2),
        operating_profit=round(tot_op, 2),
        tax_amount=round(tot_tax, 2),
        vat_amount=round(tot_vat, 2),
        net_profit=round(tot_net, 2),
        net_margin_pct=round(tot_net / tot_revenue * 100, 2) if tot_revenue else None,
        products_total=len(out_rows),
        products_with_cost=p_with_cost,
        products_missing_cost=len(out_rows) - p_with_cost,
        products_with_xlsx=p_with_xlsx,
        products_estimated=len(out_rows) - p_with_xlsx,
    )

    xlsx_coverage = (p_with_xlsx / len(out_rows) * 100) if out_rows else 0.0

    return EconomicsResp(
        period_from=date_from.isoformat(),
        period_to=date_to.isoformat(),
        tax_regime=tax_regime,
        tax_regime_label={
            "usn_income": "УСН Доходы",
            "usn_income_minus": "УСН Доходы-Расходы",
            "osno": "ОСНО",
            "none": "Без налога",
        }.get(tax_regime, tax_regime),
        tax_rate_pct=tax_rate,
        months_with_xlsx=sorted(months_covered),
        xlsx_coverage_pct=round(xlsx_coverage, 1),
        rows=out_rows, totals=totals,
    )


def _empty_totals() -> EconomicsTotals:
    return EconomicsTotals(
        qty_delivered=0, revenue=0, returned_revenue=0, effective_revenue=0,
        cost_total=0, commission_total=0,
        logistics_total=0, acquiring_total=0, ad_spend_total=0,
        storage_total=0,
        operating_profit=0, tax_amount=0, vat_amount=0, net_profit=0,
        net_margin_pct=None, products_total=0,
        products_with_cost=0, products_missing_cost=0,
        products_with_xlsx=0, products_estimated=0,
    )
