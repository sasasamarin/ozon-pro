/**
 * КОММИТ 3: графики взаимосвязей под воронкой.
 * - "Показы → Заказы" ComposedChart + scatter + lag + интерпретация
 * - "Реклама → Заказы" stacked bar + таблица типов с ДРР и подсветкой
 * - "Воронка влияний" Sankey
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, TrendingUp, AlertCircle, Info } from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Sankey,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'

interface CorrPoint {
  date: string
  impressions: number
  orders: number
  price?: number | null              // current_price (зачёркнутая до скидки)
  marketing_price?: number | null    // marketing_seller_price (цена продавца)
  customer_price?: number | null     // средняя customer_price дня (СПП-цена покупателя)
  ad_spend?: number | null           // расход на рекламу за день
  stock_total?: number | null        // остаток на конец дня
  is_stockout?: boolean
}
interface LagCorr { lag_days: number; r: number | null }
interface AnomalyPoint {
  date: string
  impressions: number
  orders: number
  reason: string
  severity: 'high' | 'medium' | 'low'
}
interface CorrelationsResp {
  period_from: string; period_to: string
  series: CorrPoint[]
  r: number | null
  elasticity: number | null
  lags: LagCorr[]
  best_lag_days: number | null
  headline: string
  explanation: string
  anomalies?: AnomalyPoint[]
  has_price_overlay?: boolean
  product_name?: string | null
}

interface AdTypeDaily { date: string; spend: number; orders: number; revenue: number }
interface AdTypeRow {
  type_key: string
  label: string
  payment_model: string
  source: 'PA-daily' | 'transactions-only'
  spend: number
  revenue: number
  orders: number
  impressions: number
  clicks: number
  ctr_pct: number | null
  cpc: number | null
  cpa: number | null
  romi_pct: number | null
  drr_pct: number | null
  daily: AdTypeDaily[]
  unknown_ozon_types: string[]
}
interface AdByTypeResp {
  period_from: string; period_to: string
  rows: AdTypeRow[]
  total_spend_pa: number
  total_spend_tx: number
  note: string
}

interface SankeyResp {
  period_from: string; period_to: string
  nodes: { name: string }[]
  links: {
    source: number; target: number; value: number
    conv_pct: number | null
    label: string
    is_bottleneck: boolean
  }[]
  bottleneck_step: string | null
}

// Палитра типов рекламы для stacked bar
const TYPE_COLOR: Record<string, string> = {
  sku: '#6366f1',
  search_promo: '#ec4899',
  banner: '#0ea5e9',
  video_banner: '#06b6d4',
  brand_shelf: '#10b981',
  ref_vk: '#f59e0b',
  global_promo: '#a855f7',
  unknown: '#94a3b8',
}

const RU_DATE = (s: string) =>
  new Date(s).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })

// =====================================================================

export function FunnelInsights({
  days,
  productIds,
  cabinetIds,
}: {
  days: number
  productIds?: string[]
  cabinetIds?: string[]
}) {
  const params = new URLSearchParams({ days: String(days) })
  if (productIds && productIds.length) productIds.forEach((p) => params.append('product_ids', p))
  if (cabinetIds && cabinetIds.length) cabinetIds.forEach((c) => params.append('cabinet_ids', c))
  const qs = params.toString()

  return (
    <div className="flex flex-col gap-5">
      <ShowsToOrdersChart qs={qs} />
      <AdByTypeChart qs={qs} />
      <SankeyChart qs={qs} />
    </div>
  )
}

// =====================================================================
// 1. Показы → Заказы
// =====================================================================

function ShowsToOrdersChart({ qs }: { qs: string }) {
  // Состояние выбора overlay-метрик. Юзер может наложить произвольный набор.
  const [overlays, setOverlays] = useState<Set<string>>(
    () => new Set(['impressions', 'orders', 'customer', 'ad_spend'])
  )
  const toggle = (k: string) =>
    setOverlays((prev) => {
      const next = new Set(prev)
      if (next.has(k)) next.delete(k)
      else next.add(k)
      return next
    })

  const { data, isLoading } = useQuery<CorrelationsResp>({
    queryKey: ['funnel', 'correlations', qs],
    queryFn: async () => (await api.get(`/analytics/funnel/v2/correlations?${qs}`)).data,
    staleTime: 60_000,
  })

  if (isLoading) return <ChartSkeleton title="Показы → Заказы" />
  if (!data || data.series.length === 0)
    return <EmptyCard title="Показы → Заказы" hint="Нет данных за выбранный период" />

  const chartData = data.series.map((p) => ({
    date: RU_DATE(p.date),
    rawDate: p.date,
    impressions: p.impressions,
    orders: p.orders,
    price: p.price ?? null,
    spp: p.marketing_price ?? null,
    customer: p.customer_price ?? null,
    ad_spend: p.ad_spend ?? null,
    stock: p.stock_total ?? null,
    is_stockout: p.is_stockout || false,
  }))

  const r = data.r
  const strengthColor =
    r === null ? 'text-fg-muted'
    : Math.abs(r) >= 0.7 ? 'text-emerald-700'
    : Math.abs(r) >= 0.4 ? 'text-amber-700'
    : 'text-rose-700'

  // Зоны стокаута для ReferenceArea
  const stockoutSpans: Array<{ x1: string; x2: string }> = []
  let span: { x1: string; x2: string } | null = null
  chartData.forEach((p, i) => {
    if (p.is_stockout) {
      if (!span) span = { x1: p.date, x2: p.date }
      else span.x2 = p.date
      if (i === chartData.length - 1 && span) stockoutSpans.push(span)
    } else if (span) {
      stockoutSpans.push(span)
      span = null
    }
  })

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between mb-4 flex-wrap gap-2">
        <div>
          <h2 className="text-lg font-semibold text-fg flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-indigo-600" />
            Показы → Заказы
            {data.product_name && (
              <span className="text-sm font-normal text-fg-muted truncate max-w-[280px]">
                · {data.product_name}
              </span>
            )}
          </h2>
          <p className="text-xs text-fg-muted mt-0.5">Как показы влияют на количество заказов</p>
        </div>
        <div className={cn('text-right', strengthColor)}>
          <div className="text-sm font-semibold">{data.headline}</div>
          {r !== null && <div className="text-xs tabular-nums">r = {r.toFixed(2)}</div>}
        </div>
      </div>

      <div className="text-sm text-fg bg-bg-subtle/40 border border-border-subtle rounded-md px-3 py-2 mb-3 flex gap-2 items-start">
        <Info className="w-4 h-4 mt-0.5 shrink-0 text-fg-muted" />
        <span>{data.explanation}</span>
      </div>

      {/* Выбор overlay-метрик. Юзер сам строит «свою зависимость». */}
      <div className="mb-3 flex flex-wrap gap-1.5 text-xs">
        <span className="text-fg-muted self-center mr-1">Слои:</span>
        {([
          ['impressions', 'Показы',          'bg-slate-400'],
          ['orders',      'Заказы',          'bg-red-500'],
          ['customer',    'СПП покупателю',  'bg-blue-600'],
          ['spp',         'Цена продавца',   'bg-purple-500'],
          ['price',       'До скидки',       'bg-emerald-500'],
          ['ad_spend',    'Реклама ₽',       'bg-amber-500'],
          ['stock',       'Остаток',         'bg-cyan-500'],
        ] as Array<[string, string, string]>).map(([key, label, color]) => {
          const active = overlays.has(key)
          return (
            <button
              key={key}
              onClick={() => toggle(key)}
              className={cn(
                'px-2 py-1 rounded-md border transition-colors flex items-center gap-1.5',
                active
                  ? 'border-fg/40 bg-bg-subtle text-fg'
                  : 'border-border-subtle text-fg-muted hover:bg-bg-subtle/50'
              )}
            >
              <span className={cn('w-2 h-2 rounded-full', color, !active && 'opacity-30')} />
              {label}
            </button>
          )
        })}
      </div>

      <div className="h-[300px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#6b7280' }} />
            <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#6b7280' }}
                   tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: '#dc2626' }} />
            {data.has_price_overlay && (
              <YAxis yAxisId="price" orientation="right" hide />
            )}
            <Tooltip
              formatter={(v: number, name: string) => {
                // ВНИМАНИЕ: в данных
                //   price = current_price = 33000 (зачёркнутая, ДО скидки)
                //   spp   = marketing_price = 19958 (цена продавца, ОТ неё считается выручка)
                //   customer = avg customer_price = 11000 (СПП-цена покупателя)
                // ПОДПИСИ ВЫРОВНЕНЫ под истинный смысл (юзер: 19958 ≠ СПП).
                if (name === 'price')    return [v ? `${formatNumber(v)} ₽` : '—', 'До скидки']
                if (name === 'spp')      return [v ? `${formatNumber(v)} ₽` : '—', 'Цена продавца']
                if (name === 'customer') return [v ? `${formatNumber(v)} ₽` : '—', 'СПП покупателю']
                if (name === 'ad_spend') return [v ? `${formatCurrency(v)}` : '—', 'Реклама ₽']
                if (name === 'stock')    return [v != null ? formatNumber(v) : '—', 'Остаток']
                if (name === 'orders') return [formatNumber(v), 'Заказы']
                if (name === 'impressions') return [formatNumber(v), 'Показы']
                return [formatNumber(v), name]
              }}
            />
            <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
                    formatter={(v: string) => (
                      v === 'impressions' ? 'Показы' :
                      v === 'orders' ? 'Заказы' :
                      v === 'price' ? 'До скидки' :
                      v === 'spp' ? 'Цена продавца' :
                      v === 'customer' ? 'СПП покупателю' :
                      v === 'ad_spend' ? 'Реклама ₽' :
                      v === 'stock' ? 'Остаток' : v
                    )} />
            {/* Красные зоны стокаута поверх */}
            {stockoutSpans.map((s, i) => (
              <ReferenceArea key={i} yAxisId="left" x1={s.x1} x2={s.x2}
                             fill="#fecaca" fillOpacity={0.4} ifOverflow="visible" />
            ))}
            {overlays.has('impressions') && (
              <Bar yAxisId="left" dataKey="impressions" fill="#cbd5e1" name="impressions" />
            )}
            {overlays.has('orders') && (
              <Line yAxisId="right" type="monotone" dataKey="orders" stroke="#dc2626"
                    strokeWidth={2} dot={false} name="orders" />
            )}
            {overlays.has('ad_spend') && (
              <Line yAxisId="right" type="monotone" dataKey="ad_spend" stroke="#f59e0b"
                    strokeWidth={2} strokeDasharray="3 2" dot={false} name="ad_spend"
                    connectNulls />
            )}
            {overlays.has('stock') && (
              <Line yAxisId="left" type="monotone" dataKey="stock" stroke="#06b6d4"
                    strokeWidth={1.5} dot={false} name="stock" connectNulls />
            )}
            {data.has_price_overlay && overlays.has('price') && (
              <Line yAxisId="price" type="monotone" dataKey="price" stroke="#10b981"
                    strokeWidth={1.5} strokeDasharray="4 3" dot={false} name="price" />
            )}
            {data.has_price_overlay && overlays.has('spp') && (
              <Line yAxisId="price" type="monotone" dataKey="spp" stroke="#a855f7"
                    strokeWidth={2} dot={false} name="spp" />
            )}
            {data.has_price_overlay && overlays.has('customer') && (
              <Line yAxisId="price" type="monotone" dataKey="customer" stroke="#2563eb"
                    strokeWidth={2} dot={{ r: 2 }} connectNulls name="customer" />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Аномалии-подсказки */}
      {data.anomalies && data.anomalies.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium text-fg mb-2 flex items-center gap-1.5">
            <AlertCircle className="w-4 h-4 text-amber-600" />
            Аномалии: «много показов, мало заказов»
          </h3>
          <div className="space-y-1.5">
            {data.anomalies.slice(0, 6).map((a) => (
              <div key={a.date} className={cn(
                'text-xs rounded-md px-3 py-1.5 border flex items-start gap-2',
                a.severity === 'high'
                  ? 'border-rose-300 bg-rose-50/60 text-rose-900'
                  : 'border-amber-300 bg-amber-50/60 text-amber-900',
              )}>
                <span className="font-mono shrink-0">{new Date(a.date).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })}</span>
                <span className="text-fg-muted tabular-nums shrink-0">
                  показов {formatNumber(a.impressions)} · заказов {a.orders}
                </span>
                <span className="ml-auto text-right">{a.reason}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-5">
        <div>
          <h3 className="text-sm font-medium text-fg mb-1">Точечный график</h3>
          <p className="text-[11px] text-fg-muted mb-2">
            <strong>Каждая точка = один день.</strong> Правее = больше показов в тот день, выше = больше заказов.
          </p>
          <div className="h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis type="number" dataKey="impressions" name="Показы"
                       tick={{ fontSize: 10, fill: '#6b7280' }}
                       tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : `${v}`} />
                <YAxis type="number" dataKey="orders" name="Заказы"
                       tick={{ fontSize: 10, fill: '#6b7280' }} />
                <ZAxis range={[40, 40]} />
                <Tooltip cursor={{ strokeDasharray: '3 3' }}
                         formatter={(v: number, name: string) =>
                           [formatNumber(v), name === 'impressions' ? 'Показы' : 'Заказы']} />
                <Scatter data={data.series} fill="#6366f1" />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <div className="text-[11px] mt-2 p-2 rounded bg-bg-subtle/60 leading-relaxed">
            <strong>Как читать:</strong>
            <ul className="list-disc list-inside mt-1 space-y-0.5 text-fg-muted">
              <li>Точки выстроились по диагонали ↗ → <span className="text-emerald-700">реклама работает</span>:
                  больше показов = больше заказов.</li>
              <li>Точки в кучу или зигзагом → заказы зависят НЕ от показов
                  (цена, сезон, отзывы, остаток).</li>
            </ul>
            {r !== null && (
              <div className="mt-1.5 pt-1.5 border-t border-border-subtle/40">
                <strong>Вывод по этому графику:</strong>{' '}
                <span className={strengthColor}>
                  {r >= 0.7 ? 'сильная связь — гнать показы стоит' :
                   r >= 0.4 ? 'средняя связь — показы влияют, но не главное' :
                   r >= 0.2 ? 'слабая связь — больше показов мало даёт' :
                   r >= -0.2 ? 'связи нет — показы НЕ драйвер заказов' :
                   'обратная связь — лишние показы скорее мешают'}
                </span>
              </div>
            )}
          </div>
        </div>

        <div>
          <h3 className="text-sm font-medium text-fg mb-2">Лаг-анализ (до 14 дней)</h3>
          <p className="text-[11px] text-fg-muted mb-2">
            Когда сегодняшние показы превращаются в заказы — сегодня, завтра, через неделю?
            Зелёный = самый сильный «отклик».
          </p>
          <div className="space-y-1">
            {data.lags.map((l) => {
              const v = l.r ?? 0
              const isBest = l.lag_days === data.best_lag_days && (l.r ?? 0) > 0
              const w = Math.min(100, Math.abs(v) * 100)
              return (
                <div key={l.lag_days} className="flex items-center gap-2 text-xs">
                  <span className="w-16 text-fg-muted">
                    {l.lag_days === 0 ? 'тот же день' : `+${l.lag_days} дн`}
                  </span>
                  <div className="flex-1 h-3.5 bg-bg-subtle rounded overflow-hidden relative">
                    <div className={cn(
                      'h-full rounded',
                      isBest ? 'bg-emerald-500' : v >= 0 ? 'bg-indigo-400' : 'bg-rose-400',
                    )} style={{ width: `${w}%` }} />
                  </div>
                  <span className={cn('w-12 text-right tabular-nums',
                    isBest ? 'text-emerald-700 font-semibold' : 'text-fg')}>
                    {l.r === null ? '—' : l.r.toFixed(2)}
                  </span>
                </div>
              )
            })}
          </div>
          <div className="text-[11px] mt-3 p-2 rounded bg-bg-subtle/60 leading-relaxed">
            <strong>Что значат цифры:</strong>
            <ul className="list-disc list-inside mt-1 space-y-0.5 text-fg-muted">
              <li><span className="font-semibold">0.7-1.0</span> — сильная связь, показы → заказы почти 1:1</li>
              <li><span className="font-semibold">0.4-0.7</span> — умеренная (показы помогают, но не одни)</li>
              <li><span className="font-semibold">0.2-0.4</span> — слабая (мало зависит от показов)</li>
              <li><span className="font-semibold">0.0-0.2</span> — нет связи</li>
              <li><span className="font-semibold">отрицательная</span> — обратная связь (редко)</li>
            </ul>
            {data.best_lag_days !== null && (
              <div className="mt-1.5 pt-1.5 border-t border-border-subtle/40">
                <strong>Вывод:</strong>{' '}
                {data.best_lag_days === 0
                  ? 'показы конвертятся в заказы в тот же день — быстрый отклик'
                  : `показы дают эффект через ${data.best_lag_days} ${
                      data.best_lag_days === 1 ? 'день' : 'дн'
                    } — реклама работает с лагом, планируй заранее`}
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  )
}

// =====================================================================
// 2. Реклама → Заказы по типам
// =====================================================================

function AdByTypeChart({ qs }: { qs: string }) {
  const { data, isLoading } = useQuery<AdByTypeResp>({
    queryKey: ['funnel', 'ad-by-type', qs],
    queryFn: async () => (await api.get(`/analytics/funnel/v2/ad-by-type?${qs}`)).data,
    staleTime: 60_000,
  })
  const [hoverUnknown, setHoverUnknown] = useState(false)

  if (isLoading) return <ChartSkeleton title="Реклама → Заказы по типам" />
  if (!data || data.rows.length === 0)
    return <EmptyCard title="Реклама → Заказы по типам" hint="За период нет рекламных трат" />

  const dailyRows = data.rows.filter((r) => r.source === 'PA-daily' && r.daily.length > 0)
  const txOnlyRows = data.rows.filter((r) => r.source === 'transactions-only')

  // Pivot: по датам сумма spend каждой PA-категории
  const dateSet = new Set<string>()
  dailyRows.forEach((r) => r.daily.forEach((d) => dateSet.add(d.date)))
  const dates = [...dateSet].sort()
  const dailyData = dates.map((d) => {
    const row: Record<string, number | string> = { date: RU_DATE(d) }
    for (const r of dailyRows) {
      const dp = r.daily.find((x) => x.date === d)
      row[r.type_key] = dp ? dp.spend : 0
    }
    return row
  })

  const fmtPct = (p: number | null) => p === null ? '—' : `${p.toFixed(2)}%`
  const colorByDRR = (drr: number | null) => {
    if (drr === null) return 'text-fg-muted'
    if (drr < 5) return 'text-emerald-700 bg-emerald-50'
    if (drr < 10) return 'text-amber-700 bg-amber-50'
    return 'text-rose-700 bg-rose-50'
  }

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between mb-3 flex-wrap gap-2">
        <div>
          <h2 className="text-lg font-semibold text-fg">Реклама → Заказы по типам</h2>
          <p className="text-xs text-fg-muted mt-0.5">{data.note}</p>
        </div>
        <div className="text-right text-xs text-fg-muted">
          <div>PA daily: <span className="text-fg font-semibold tabular-nums">{formatCurrency(data.total_spend_pa)}</span></div>
          <div>Transactions: <span className="text-fg font-semibold tabular-nums">{formatCurrency(data.total_spend_tx)}</span></div>
        </div>
      </div>

      {dailyData.length > 0 && (
        <div className="h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={dailyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis tick={{ fontSize: 11, fill: '#6b7280' }}
                     tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v} />
              <Tooltip formatter={(v: number, name) => [formatCurrency(v), labelFor(name as string, data.rows)]} />
              <Legend wrapperStyle={{ fontSize: 11, paddingTop: 6 }}
                      formatter={(v) => labelFor(v as string, data.rows)} />
              {dailyRows.map((r) => (
                <Bar key={r.type_key} dataKey={r.type_key} stackId="ads"
                     fill={TYPE_COLOR[r.type_key] || '#94a3b8'} name={r.type_key} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Таблица типов с ДРР */}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-bg-subtle/40 border-y border-border-subtle">
            <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
              <th className="py-2 px-2 font-medium">Тип</th>
              <th className="py-2 px-2 font-medium text-right">Показы</th>
              <th className="py-2 px-2 font-medium text-right">Клики</th>
              <th className="py-2 px-2 font-medium text-right">CTR</th>
              <th className="py-2 px-2 font-medium text-right">Заказы</th>
              <th className="py-2 px-2 font-medium text-right">Расход</th>
              <th className="py-2 px-2 font-medium text-right">Выручка</th>
              <th className="py-2 px-2 font-medium text-right">CPC</th>
              <th className="py-2 px-2 font-medium text-right">CPA</th>
              <th className="py-2 px-2 font-medium text-right">ДРР</th>
              <th className="py-2 px-2 font-medium text-right">ROMI</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {data.rows.map((r) => {
              const isUnknown = r.type_key === 'unknown' && r.unknown_ozon_types.length > 0
              const romiCls =
                r.romi_pct === null ? 'text-fg-muted' :
                r.romi_pct >= 100 ? 'text-emerald-700' :
                r.romi_pct >= 0   ? 'text-amber-700' :
                'text-rose-700'
              return (
                <tr key={r.type_key} className="hover:bg-bg-subtle/30 align-middle">
                  <td className="py-2 px-2">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="w-2.5 h-2.5 rounded-sm shrink-0"
                            style={{ backgroundColor: TYPE_COLOR[r.type_key] || '#94a3b8' }} />
                      <div className="flex flex-col min-w-0">
                        <span className="text-fg truncate" title={r.label}>{r.label}</span>
                        <span className="text-[10px] text-fg-muted">
                          {r.payment_model}
                          {' · '}
                          <span className={cn(
                            r.source === 'PA-daily' ? 'text-indigo-700' : 'text-slate-500'
                          )}>
                            {r.source === 'PA-daily' ? 'PA daily' : 'tx only'}
                          </span>
                        </span>
                      </div>
                      {isUnknown && (
                        <span
                          className="text-[10px] px-1 py-0.5 rounded bg-slate-100 text-slate-600 cursor-help shrink-0"
                          onMouseEnter={() => setHoverUnknown(true)}
                          onMouseLeave={() => setHoverUnknown(false)}
                          title={r.unknown_ozon_types.join(', ')}
                        >
                          {r.unknown_ozon_types.length} новых
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-2 px-2 text-right tabular-nums">{r.impressions ? formatNumber(r.impressions) : '—'}</td>
                  <td className="py-2 px-2 text-right tabular-nums">{r.clicks ? formatNumber(r.clicks) : '—'}</td>
                  <td className="py-2 px-2 text-right tabular-nums text-fg-muted">{r.ctr_pct === null ? '—' : `${r.ctr_pct.toFixed(2)}%`}</td>
                  <td className="py-2 px-2 text-right tabular-nums">{r.orders ? formatNumber(r.orders) : '—'}</td>
                  <td className="py-2 px-2 text-right tabular-nums">{formatCurrency(r.spend)}</td>
                  <td className="py-2 px-2 text-right tabular-nums">{r.revenue ? formatCurrency(r.revenue) : '—'}</td>
                  <td className="py-2 px-2 text-right tabular-nums text-fg-muted">{r.cpc === null ? '—' : `${r.cpc.toFixed(0)}₽`}</td>
                  <td className="py-2 px-2 text-right tabular-nums text-fg-muted">{r.cpa === null ? '—' : `${r.cpa.toFixed(0)}₽`}</td>
                  <td className="py-2 px-2 text-right">
                    {r.drr_pct === null ? (
                      <span className="text-fg-muted">—</span>
                    ) : (
                      <span className={cn('text-xs font-medium px-1.5 py-0.5 rounded tabular-nums', colorByDRR(r.drr_pct))}>
                        {fmtPct(r.drr_pct)}
                      </span>
                    )}
                  </td>
                  <td className={cn("py-2 px-2 text-right tabular-nums font-semibold", romiCls)}>
                    {r.romi_pct === null ? '—' : `${r.romi_pct.toFixed(0)}%`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {hoverUnknown && (
        <p className="text-[11px] text-fg-muted mt-2 italic">
          Покажи такой тип Ozon’у — возможно, появился новый формат рекламы.
        </p>
      )}

      {txOnlyRows.length > 0 && (
        <p className="text-[11px] text-fg-muted mt-3 flex gap-1.5 items-start">
          <AlertCircle className="w-3.5 h-3.5 mt-px shrink-0 text-amber-600" />
          <span>
            Баннеры/брендовая полка/бейджи показаны только суммой —
            Performance API не отдаёт по ним дневную статистику.
          </span>
        </p>
      )}
    </Card>
  )
}

function labelFor(type_key: string, rows: AdTypeRow[]): string {
  return rows.find((r) => r.type_key === type_key)?.label || type_key
}

// =====================================================================
// 3. Sankey
// =====================================================================

function SankeyChart({ qs }: { qs: string }) {
  const { data, isLoading } = useQuery<SankeyResp>({
    queryKey: ['funnel', 'sankey', qs],
    queryFn: async () => (await api.get(`/analytics/funnel/v2/sankey?${qs}`)).data,
    staleTime: 60_000,
  })

  if (isLoading) return <ChartSkeleton title="Воронка влияний" />
  if (!data || data.links.length === 0)
    return <EmptyCard title="Воронка влияний" hint="Нет данных" />

  // Sankey recharts ожидает {nodes, links} с source/target index.
  // Дополнительно прокидываем conv_pct/is_bottleneck через link, чтобы рендерить.
  const sankeyData = {
    nodes: data.nodes.map((n) => ({ name: n.name })),
    links: data.links.map((l) => ({
      source: l.source,
      target: l.target,
      value: Math.max(l.value, 1),
      __conv: l.conv_pct,
      __label: l.label,
      __bottleneck: l.is_bottleneck,
    })),
  }

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between mb-3 flex-wrap gap-2">
        <div>
          <h2 className="text-lg font-semibold text-fg">Воронка влияний</h2>
          <p className="text-xs text-fg-muted mt-0.5">
            Толщина потока = число единиц. % на каждом переходе. Красный = узкое горлышко.
          </p>
        </div>
        {data.bottleneck_step && (
          <div className="text-xs px-2.5 py-1 rounded-md bg-rose-50 text-rose-700 font-medium">
            🚨 Узкое горлышко: {data.bottleneck_step}
          </div>
        )}
      </div>

      <div className="h-[320px]">
        <ResponsiveContainer width="100%" height="100%">
          <Sankey
            data={sankeyData}
            node={({ x, y, width, height, payload }: any) => (
              <g>
                <rect x={x} y={y} width={width} height={height} fill="#6366f1" rx={2} />
                <text x={x + width + 6} y={y + height / 2} textAnchor="start"
                      alignmentBaseline="middle" fontSize={12} fill="#111827" fontWeight={500}>
                  {payload.name}
                </text>
                <text x={x + width + 6} y={y + height / 2 + 14} textAnchor="start"
                      alignmentBaseline="middle" fontSize={10} fill="#6b7280">
                  {formatNumber(payload.value)}
                </text>
              </g>
            )}
            link={(linkProps: any) => {
              const { sourceX, targetX, sourceY, targetY, sourceControlX, targetControlX,
                      linkWidth, payload } = linkProps
              const isBottleneck = payload?.__bottleneck
              const stroke = isBottleneck ? '#fda4af' : '#cbd5e1'
              const path = `
                M${sourceX},${sourceY}
                C${sourceControlX},${sourceY} ${targetControlX},${targetY} ${targetX},${targetY}
              `
              const midX = (sourceX + targetX) / 2
              const midY = (sourceY + targetY) / 2
              return (
                <g>
                  <path d={path} fill="none" stroke={stroke}
                        strokeWidth={Math.max(linkWidth, 1)}
                        strokeOpacity={isBottleneck ? 0.7 : 0.45} />
                  <text x={midX} y={midY - 4} textAnchor="middle" fontSize={11}
                        fontWeight={isBottleneck ? 600 : 500}
                        fill={isBottleneck ? '#be123c' : '#374151'}>
                    {payload?.__label || `${(payload?.__conv || 0).toFixed(1)}%`}
                  </text>
                </g>
              )
            }}
            nodePadding={32}
            margin={{ top: 14, right: 110, bottom: 14, left: 10 }}
          >
            <Tooltip formatter={(v: number) => formatNumber(v)} />
          </Sankey>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

// =====================================================================

function ChartSkeleton({ title }: { title: string }) {
  return (
    <Card className="p-5">
      <h2 className="text-lg font-semibold text-fg mb-3">{title}</h2>
      <div className="h-[280px] flex items-center justify-center text-fg-muted">
        <Loader2 className="w-5 h-5 animate-spin" />
      </div>
    </Card>
  )
}

function EmptyCard({ title, hint }: { title: string; hint: string }) {
  return (
    <Card className="p-5">
      <h2 className="text-lg font-semibold text-fg">{title}</h2>
      <p className="text-sm text-fg-muted mt-2">{hint}</p>
    </Card>
  )
}
