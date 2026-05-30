/**
 * /orders — график «Заказано» по дням в стиле Ozon.
 * Сплошная линия = текущий период, пунктир = прошлый.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { TrendingUp, TrendingDown, Loader2 } from 'lucide-react'
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'

interface DailyPoint {
  date: string
  orders: number
  units: number
  revenue: number
  avg_check: number
}

interface DailyResp {
  period_from: string
  period_to: string
  series: DailyPoint[]
  prev_period_series: DailyPoint[]
  total_orders: number
  total_units: number
  total_revenue: number
  delta_orders_pct: number | null
  delta_revenue_pct: number | null
}

const RU_DATE = (s: string) =>
  new Date(s).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })

export function OrdersDailyChart({ cabinetIds }: { cabinetIds: string[] }) {
  const [days, setDays] = useState(28)
  const { data, isLoading } = useQuery<DailyResp>({
    queryKey: ['orders-daily', cabinetIds, days],
    queryFn: async () => {
      const p = new URLSearchParams({ days: String(days) })
      cabinetIds.forEach((id) => p.append('cabinet_ids', id))
      return (await api.get(`/orders/daily?${p.toString()}`)).data
    },
    staleTime: 60_000,
  })

  if (isLoading) {
    return (
      <Card className="p-5">
        <div className="h-[240px] flex items-center justify-center text-fg-muted">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      </Card>
    )
  }
  if (!data || data.series.length === 0) {
    return (
      <Card className="p-5">
        <p className="text-sm text-fg-muted">Нет данных за период</p>
      </Card>
    )
  }

  // Совмещаем series + prev в один dataset по индексу дня
  const merged: any[] = data.series.map((p, i) => ({
    date: RU_DATE(p.date),
    revenue: p.revenue,
    units: p.units,
    prev_revenue: data.prev_period_series[i]?.revenue ?? null,
  }))

  const deltaRevCls =
    data.delta_revenue_pct === null ? 'text-fg-muted' :
    data.delta_revenue_pct >= 0 ? 'text-emerald-700' : 'text-rose-700'
  const deltaOrdCls =
    data.delta_orders_pct === null ? 'text-fg-muted' :
    data.delta_orders_pct >= 0 ? 'text-emerald-700' : 'text-rose-700'

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between mb-3 flex-wrap gap-2">
        <div>
          <h2 className="text-lg font-semibold text-fg">Заказано по дням</h2>
          <p className="text-xs text-fg-muted mt-0.5">
            Сплошная линия — текущий период · пунктир — прошлый
          </p>
        </div>
        <div className="flex gap-1">
          {[7, 28, 30, 90].map((d) => (
            <button key={d} onClick={() => setDays(d)} className={cn(
              'px-2.5 py-1 rounded text-xs border',
              days === d ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle',
            )}>{d}д</button>
          ))}
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <KPI label="Сумма" value={formatCurrency(data.total_revenue)}
             delta={data.delta_revenue_pct} cls={deltaRevCls} />
        <KPI label="Заказов" value={formatNumber(data.total_orders)}
             delta={data.delta_orders_pct} cls={deltaOrdCls} />
        <KPI label="Шт." value={formatNumber(data.total_units)} />
        <KPI label="Средний чек"
             value={data.total_orders ? formatCurrency(data.total_revenue / data.total_orders) : '—'} />
      </div>

      <div className="h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={merged}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} />
            <YAxis tick={{ fontSize: 11, fill: '#6b7280' }}
                   tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : `${v}`} />
            <Tooltip formatter={(v: number, name: string) => {
              if (name === 'revenue') return [formatCurrency(v), 'Сумма']
              if (name === 'prev_revenue') return [formatCurrency(v), 'Прошлый период']
              if (name === 'units') return [formatNumber(v), 'Шт']
              return [v, name]
            }} />
            <Legend wrapperStyle={{ fontSize: 11, paddingTop: 6 }}
                    formatter={(v: string) =>
                      v === 'revenue' ? 'Сумма' :
                      v === 'prev_revenue' ? 'Прошлый период' :
                      v} />
            <Line type="monotone" dataKey="revenue" stroke="#6366f1"
                  strokeWidth={2.5} dot={false} name="revenue" />
            <Line type="monotone" dataKey="prev_revenue" stroke="#94a3b8"
                  strokeWidth={1.5} strokeDasharray="5 4" dot={false} name="prev_revenue" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

function KPI({
  label, value, delta, cls,
}: {
  label: string
  value: string
  delta?: number | null
  cls?: string
}) {
  return (
    <div className="rounded-md border border-border-subtle bg-bg-subtle/30 px-3 py-2">
      <div className="text-[10px] font-medium text-fg-muted uppercase tracking-wider">{label}</div>
      <div className="text-base font-semibold text-fg mt-0.5 tabular-nums">{value}</div>
      {delta !== undefined && delta !== null && (
        <div className={cn('text-[11px] tabular-nums flex items-center gap-0.5 mt-0.5', cls)}>
          {delta >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
          {delta > 0 ? '+' : ''}{delta.toFixed(1)}%
        </div>
      )}
    </div>
  )
}
