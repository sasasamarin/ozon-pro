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
  Cell,
  ComposedChart,
  Legend,
  Line,
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

interface CorrPoint { date: string; impressions: number; orders: number }
interface LagCorr { lag_days: number; r: number | null }
interface CorrelationsResp {
  period_from: string; period_to: string
  series: CorrPoint[]
  r: number | null
  elasticity: number | null
  lags: LagCorr[]
  best_lag_days: number | null
  headline: string
  explanation: string
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
  links: { source: number; target: number; value: number }[]
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
  productId,
  cabinetIds,
}: {
  days: number
  productId?: string
  cabinetIds?: string[]
}) {
  const params = new URLSearchParams({ days: String(days) })
  if (productId) params.set('product_id', productId)
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
    impressions: p.impressions,
    orders: p.orders,
  }))

  const r = data.r
  const strengthColor =
    r === null ? 'text-fg-muted'
    : Math.abs(r) >= 0.7 ? 'text-emerald-700'
    : Math.abs(r) >= 0.4 ? 'text-amber-700'
    : 'text-rose-700'

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between mb-4 flex-wrap gap-2">
        <div>
          <h2 className="text-lg font-semibold text-fg flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-indigo-600" />
            Показы → Заказы
          </h2>
          <p className="text-xs text-fg-muted mt-0.5">Как показы влияют на количество заказов</p>
        </div>
        <div className={cn('text-right', strengthColor)}>
          <div className="text-sm font-semibold">{data.headline}</div>
          {r !== null && <div className="text-xs tabular-nums">r = {r.toFixed(2)}</div>}
        </div>
      </div>

      <div className="text-sm text-fg bg-bg-subtle/40 border border-border-subtle rounded-md px-3 py-2 mb-4 flex gap-2 items-start">
        <Info className="w-4 h-4 mt-0.5 shrink-0 text-fg-muted" />
        <span>{data.explanation}</span>
      </div>

      <div className="h-[280px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#6b7280' }} />
            <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#6b7280' }}
                   tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: '#dc2626' }} />
            <Tooltip
              formatter={(v: number, name) =>
                [formatNumber(v), name === 'impressions' ? 'Показы' : 'Заказы']
              }
            />
            <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
                    formatter={(v) => (v === 'impressions' ? 'Показы' : 'Заказы')} />
            <Bar yAxisId="left" dataKey="impressions" fill="#cbd5e1" name="impressions" />
            <Line yAxisId="right" type="monotone" dataKey="orders" stroke="#dc2626"
                  strokeWidth={2} dot={false} name="orders" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-5">
        <div>
          <h3 className="text-sm font-medium text-fg mb-2">Точечный график (показы × заказы)</h3>
          <div className="h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis type="number" dataKey="impressions" name="Показы"
                       tick={{ fontSize: 10, fill: '#6b7280' }}
                       tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v} />
                <YAxis type="number" dataKey="orders" name="Заказы"
                       tick={{ fontSize: 10, fill: '#6b7280' }} />
                <ZAxis range={[40, 40]} />
                <Tooltip cursor={{ strokeDasharray: '3 3' }}
                         formatter={(v: number, name) =>
                           [formatNumber(v), name === 'impressions' ? 'Показы' : 'Заказы']} />
                <Scatter data={data.series} fill="#6366f1" />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div>
          <h3 className="text-sm font-medium text-fg mb-2">Лаг-анализ корреляции</h3>
          <p className="text-[11px] text-fg-muted mb-2">
            r показывает связь «показы сегодня → заказы через N дней»
          </p>
          <div className="space-y-2">
            {data.lags.map((l) => {
              const v = l.r ?? 0
              const isBest = l.lag_days === data.best_lag_days && (l.r ?? 0) > 0
              const w = Math.min(100, Math.abs(v) * 100)
              return (
                <div key={l.lag_days} className="flex items-center gap-2 text-xs">
                  <span className="w-14 text-fg-muted">
                    {l.lag_days === 0 ? 'тот же день' : `через ${l.lag_days} дн`}
                  </span>
                  <div className="flex-1 h-4 bg-bg-subtle rounded overflow-hidden relative">
                    <div className={cn(
                      'h-full rounded',
                      isBest ? 'bg-emerald-500' : v >= 0 ? 'bg-indigo-400' : 'bg-rose-400',
                    )} style={{ width: `${w}%` }} />
                  </div>
                  <span className={cn('w-14 text-right tabular-nums',
                    isBest ? 'text-emerald-700 font-semibold' : 'text-fg')}>
                    {l.r === null ? '—' : l.r.toFixed(2)}
                  </span>
                </div>
              )
            })}
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
              <th className="py-2 px-3 font-medium">Тип</th>
              <th className="py-2 px-3 font-medium">Оплата</th>
              <th className="py-2 px-3 font-medium">Источник</th>
              <th className="py-2 px-3 font-medium text-right">Расход</th>
              <th className="py-2 px-3 font-medium text-right">Заказов</th>
              <th className="py-2 px-3 font-medium text-right">Выручка</th>
              <th className="py-2 px-3 font-medium text-right">ДРР</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {data.rows.map((r) => {
              const isUnknown = r.type_key === 'unknown' && r.unknown_ozon_types.length > 0
              return (
                <tr key={r.type_key} className="hover:bg-bg-subtle/30 align-middle">
                  <td className="py-2 px-3">
                    <span className="inline-flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-sm shrink-0"
                            style={{ backgroundColor: TYPE_COLOR[r.type_key] || '#94a3b8' }} />
                      <span className="text-fg">{r.label}</span>
                      {isUnknown && (
                        <span
                          className="text-[10px] px-1 py-0.5 rounded bg-slate-100 text-slate-600 cursor-help"
                          onMouseEnter={() => setHoverUnknown(true)}
                          onMouseLeave={() => setHoverUnknown(false)}
                          title={r.unknown_ozon_types.join(', ')}
                        >
                          {r.unknown_ozon_types.length} новых типа Ozon
                        </span>
                      )}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-fg-muted">{r.payment_model}</td>
                  <td className="py-2 px-3">
                    <span className={cn(
                      'text-[10px] px-1.5 py-0.5 rounded',
                      r.source === 'PA-daily'
                        ? 'bg-indigo-50 text-indigo-700'
                        : 'bg-slate-100 text-slate-600',
                    )}>
                      {r.source === 'PA-daily' ? 'PA (по дням)' : 'Транзакции (только итог)'}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums">{formatCurrency(r.spend)}</td>
                  <td className="py-2 px-3 text-right tabular-nums">{r.orders ? formatNumber(r.orders) : '—'}</td>
                  <td className="py-2 px-3 text-right tabular-nums">
                    {r.revenue ? formatCurrency(r.revenue) : '—'}
                  </td>
                  <td className="py-2 px-3 text-right">
                    {r.drr_pct === null ? (
                      <span className="text-fg-muted">—</span>
                    ) : (
                      <span className={cn('text-xs font-medium px-2 py-0.5 rounded tabular-nums', colorByDRR(r.drr_pct))}>
                        {fmtPct(r.drr_pct)}
                      </span>
                    )}
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

  // Sankey recharts ожидает {nodes, links} (links уже с source/target index).
  const sankeyData = {
    nodes: data.nodes.map((n) => ({ name: n.name })),
    links: data.links.map((l) => ({ source: l.source, target: l.target, value: Math.max(l.value, 1) })),
  }

  return (
    <Card className="p-5">
      <h2 className="text-lg font-semibold text-fg">Воронка влияний</h2>
      <p className="text-xs text-fg-muted mt-0.5 mb-3">
        Толщина потока = количество единиц. Видно, где сужается «горлышко».
      </p>

      <div className="h-[280px]">
        <ResponsiveContainer width="100%" height="100%">
          <Sankey
            data={sankeyData}
            node={({ x, y, width, height, index, payload }: any) => (
              <g>
                <rect x={x} y={y} width={width} height={height} fill="#6366f1" rx={2} />
                <text x={x + width + 6} y={y + height / 2} textAnchor="start"
                      alignmentBaseline="middle" fontSize={12} fill="#111827">
                  {payload.name}
                </text>
                <text x={x + width + 6} y={y + height / 2 + 14} textAnchor="start"
                      alignmentBaseline="middle" fontSize={10} fill="#6b7280">
                  {formatNumber(payload.value)}
                </text>
              </g>
            )}
            link={{ stroke: '#cbd5e1' }}
            nodePadding={28}
            margin={{ top: 10, right: 110, bottom: 10, left: 10 }}
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
