/**
 * Реестр метрик с описаниями.
 *
 * Принцип #3 из CLAUDE.md: «У каждой метрики описание: что, почему,
 * по каким дням смотреть, факт или оценка.»
 *
 * Используется через <MetricLabel metricKey="..." /> и <MetricTooltip>.
 */

export type MetricSource =
  | 'api'        // факт из Ozon API
  | 'xlsx'       // из ручного XLSX
  | 'estimated'  // оценка / pro-rata
  | 'manual'     // юзер ввёл руками
  | 'derived'    // считается из факт-метрик внутри Flowoi
  | 'mixed'      // комбинация (например, api + estimated)

export interface MetricInfo {
  /** Короткий человеческий лейбл (на карточке). */
  label: string
  /** 1-2 предложения — что это. */
  description: string
  /** Формула, если есть. Plain-text. */
  formula?: string
  /** Откуда берётся. */
  source: MetricSource
  /** Когда смотреть имеет смысл. */
  whenToCheck?: string
  /** На что обратить внимание / типичные ошибки интерпретации. */
  cautions?: string[]
  /** Ссылка на детальный раздел. */
  link?: string
}

/** Лейблы источников для UI. */
export const SOURCE_LABEL: Record<MetricSource, { label: string; tone: string }> = {
  api:       { label: 'факт API',  tone: 'bg-emerald-100 text-emerald-700' },
  xlsx:      { label: 'факт XLSX', tone: 'bg-blue-100 text-blue-700' },
  estimated: { label: '≈ оценка',  tone: 'bg-amber-100 text-amber-700' },
  manual:    { label: 'вручную',   tone: 'bg-purple-100 text-purple-700' },
  derived:   { label: 'расчёт',    tone: 'bg-slate-100 text-slate-700' },
  mixed:     { label: 'смешанно',  tone: 'bg-orange-100 text-orange-700' },
}

export const METRICS: Record<string, MetricInfo> = {
  // === Выручка / продажи ===
  revenue: {
    label: 'Выручка',
    description: 'Деньги, начисленные продавцу за доставленные заказы.',
    formula: 'sum(accruals_for_sale) WHERE operation_type=OperationAgentDeliveredToCustomer',
    source: 'api',
    whenToCheck: 'Ежедневно. Расхождение с кабинетом Ozon = баг.',
    cautions: ['СПП не вычитается из выручки продавца — её платит Ozon из своего кармана.',
               'Возвраты учитываются отдельной операцией (OperationReturnGoodsFBS) — смотри Returns.'],
    link: '/finance/pnl',
  },
  seller_revenue: {
    label: 'Выручка продавца',
    description: 'Полная выручка с учётом баллов и партнёрских программ — то, что реально получает продавец до удержаний.',
    formula: 'Выручка + Баллы за скидки + Программы партнёров',
    source: 'derived',
    cautions: ['Баллы за скидки — это ПРИТОК (Ozon возмещает), а не расход. Часто путают.'],
    link: '/finance/pnl',
  },
  orders_count: {
    label: 'Заказы (доставлено)',
    description: 'Количество доставленных заказов за период.',
    formula: 'COUNT(*) FROM orders WHERE status=delivered',
    source: 'api',
    whenToCheck: 'Ежедневно после 23:59 — это закрытый день.',
    cautions: ['Один posting = один заказ. SKU внутри posting считаются отдельно (см. order_items).'],
    link: '/orders',
  },
  delivered_count: {
    label: 'Выкуплено единиц',
    description: 'Сколько единиц (штук) реально выкупили покупатели.',
    formula: 'SUM(order_items.quantity) WHERE status=delivered',
    source: 'api',
    whenToCheck: 'Используется для расчёта оборачиваемости и точной маржи.',
  },
  aov: {
    label: 'Средний чек',
    description: 'Средняя стоимость одного доставленного заказа.',
    formula: 'revenue / orders_count',
    source: 'derived',
    cautions: ['Завышается при большом числе бандлов / multi-SKU postings.'],
  },

  // === Прибыль / маржа ===
  gross_profit: {
    label: 'Прибыль до налога',
    description: 'Прибыль продавца после всех расходов Ozon, до уплаты налога.',
    formula: 'seller_revenue − комиссия − логистика − хранение − реклама − эквайринг − last_mile − return_logistics − себестоимость',
    source: 'derived',
    whenToCheck: 'После полного импорта transactions за месяц (5-7 число следующего месяца).',
    cautions: ['Если у SKU нет cost_price — себестоимость не вычитается, прибыль завышена.',
               'Смотри /finance/pnl для разбивки по операционному / отчётному контурам.'],
    link: '/finance/pnl',
  },
  net_profit: {
    label: 'Чистая прибыль',
    description: 'Прибыль после уплаты налога.',
    formula: 'gross_profit − tax (по выбранному режиму)',
    source: 'derived',
    cautions: ['Налог — оценка по настройкам компании. Точная сумма — после закрытия квартала.'],
    link: '/finance/taxes',
  },
  gross_margin_pct: {
    label: 'Маржа %',
    description: 'Валовая маржа в процентах от выручки.',
    formula: '(seller_price − cost_price − средние МП-расходы) / seller_price × 100',
    source: 'mixed',
    cautions: ['МП-расходы по умолчанию = коэффициенты, см. /finance/unit-economy для точного расчёта.',
               'SKU без cost_price исключены из расчёта.'],
    link: '/finance/margin',
  },
  cost_price: {
    label: 'Себестоимость',
    description: 'Закупочная стоимость одной единицы товара (без логистики до склада).',
    source: 'manual',
    cautions: ['Заведи на /products/economics или через supplier_orders.',
               'Себестоимость на дату продажи берётся из product_cost_history.'],
    link: '/products/economics',
  },

  // === Расходы Ozon ===
  ozon_expenses: {
    label: 'Расходы Ozon',
    description: 'Все удержания Ozon: комиссия, логистика, хранение, реклама, эквайринг и т.д.',
    formula: 'SUM(|amount|) WHERE amount<0 в transactions',
    source: 'api',
    cautions: ['Includes операции по гибкому графику Ozon.Invest — это финансирование, не расход. См. /finance/cashflow для cashflow.'],
    link: '/finance/transactions',
  },
  expense_share_pct: {
    label: 'Доля расходов',
    description: 'Какую долю выручки забирает Ozon.',
    formula: 'ozon_expenses / revenue × 100',
    source: 'derived',
    cautions: ['Норма для FBO ≈ 35-45%, для FBS ≈ 20-30%.'],
  },
  commission: {
    label: 'Комиссия Ozon',
    description: 'Процент Ozon от продажи (зависит от категории).',
    source: 'api',
    cautions: ['Часто меняется — Ozon уведомляет за 30 дней. См. алерт COMMISSION_CHANGE.'],
  },

  // === Склад / остатки ===
  stock_for_sale: {
    label: 'Остаток к продаже',
    description: 'Единицы, доступные для покупки прямо сейчас (по всем складам).',
    source: 'api',
    whenToCheck: 'Ежедневно перед закупкой. Снимок снимаем раз в сутки в 02:30 UTC.',
    cautions: ['История по складам — ведём сами, Ozon отдаёт только текущий snapshot.'],
    link: '/products',
  },
  days_left: {
    label: 'Дней до 0',
    description: 'Сколько дней остатков хватит при текущей скорости продаж.',
    formula: 'stock_for_sale / avg_daily_sales',
    source: 'derived',
    cautions: ['avg_daily_sales — скользящее за 14 дней. На новых SKU неточно.'],
    link: '/analytics/stockouts',
  },

  // === Воронка ===
  funnel_conversion: {
    label: 'Конверсия',
    description: 'Доля посетителей, дошедших до покупки.',
    formula: 'orders / hits × 100',
    source: 'api',
    cautions: ['Premium-only метрика. На обычной подписке Ozon отдаёт только агрегаты.'],
    link: '/analytics/funnel',
  },

  // === Кредиты / cashflow ===
  dscr: {
    label: 'DSCR',
    description: 'Debt Service Coverage Ratio — во сколько раз cashflow покрывает платёж.',
    formula: 'net_cashflow / loan_payment',
    source: 'derived',
    cautions: ['Прогноз cashflow — proxy: тот же месяц годом ранее. На новом бизнесе неточно.',
               'DSCR ≥ 1.5 = безопасно; 1-1.5 = напряжённо; < 1 = перегрузка.'],
    link: '/credits/cashflow-impact',
  },

  // === Возвраты / качество ===
  return_rate_pct: {
    label: '% возвратов',
    description: 'Доля возвратов от количества доставленных единиц.',
    formula: 'returns / delivered_units × 100',
    source: 'api',
    cautions: ['Не различает «дефект» и «не подошёл». Для детализации — /procurement/quality.'],
    link: '/procurement/quality',
  },

  // === Реклама ===
  ad_spend: {
    label: 'Расход на рекламу',
    description: 'Деньги, потраченные на рекламные кампании Ozon.',
    source: 'api',
    cautions: ['Performance API отдаёт ДРР отдельно от Seller API. См. /finance/p-and-l для итога.'],
    link: '/finance/expenses',
  },
  drr: {
    label: 'ДРР',
    description: 'Доля рекламных расходов — доля выручки, потраченная на рекламу.',
    formula: 'ad_spend / revenue × 100',
    source: 'derived',
    cautions: ['Норма 5-15% — выше может означать неэффективную кампанию.'],
  },
}

/** Безопасный доступ — undefined если ключа нет. */
export function getMetricInfo(key: string): MetricInfo | undefined {
  return METRICS[key]
}
