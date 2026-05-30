/**
 * КОММИТ 3 (4): Остаток → Продажи + красные зоны стокаута + цена потерь.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Loader2, Package, TrendingDown } from 'lucide-react'
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'

interface StockSalesPoint {
  date: string
  stock: number
  sales: number
  is_stockout: boolean
  revenue: number
}
interface StockoutPeriod {
  start: string
  end: string
  days: number
  lost_units_estimate: number
  lost_revenue_estimate: number
}
interface StockSalesResp {
  product_id: string
  product_name: string | null
  period_from: string
  period_to: string
  history_days_available: number
  earliest_stock_date: string | null
  series: StockSalesPoint[]
  stockout_periods: StockoutPeriod[]
  total_stockout_days: number
  total_lost_units: number
  total_lost_revenue: number
  avg_daily_velocity_units: number
  avg_unit_price: number
}

const RU_DATE = (s: string) =>
  new Date(s).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })

export function StockSalesChart({ productId }: { productId: string }) {
  const [days, setDays] = useState(90)
  const { data, isLoading } = useQuery<StockSalesResp>({
    queryKey: ['product', productId, 'stock-sales', days],
    queryFn: async () =>
      (await api.get(`/products/${productId}/stock-sales?days=${days}`)).data,
    staleTime: 60_000,
  })

  if (isLoading) {
    return (
      <Card className="p-5">
        <h2 className="text-lg font-semibold text-fg mb-3 flex items-center gap-2">
          <Package className="w-4 h-4 text-indigo-600" />
          Остаток → Продажи
        </h2>
        <div className="h-[280px] flex items-center justify-center text-fg-muted">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      </Card>
    )
  }

  if (!data || data.series.length === 0) {
    return (
      <Card className="p-5">
        <h2 className="text-lg font-semibold text-fg flex items-center gap-2">
          <Package className="w-4 h-4" /> Остаток → Продажи
        </h2>
        <p className="text-sm text-fg-muted mt-2">Нет истории остатков для этого товара</p>
      </Card>
    )
  }

  const chartData = data.series.map((p, idx) => ({
    idx,
    date: RU_DATE(p.date),
    rawDate: p.date,
    stock: p.stock,
    sales: p.sales,
    isStockout: p.is_stockout,
  }))

  // ReferenceArea — для каждого периода стокаута
  // Нужно знать индекс start и end в chartData
  const dateToIdx = new Map(chartData.map((p, i) => [p.rawDate, i]))
  const stockoutSpans = data.stockout_periods
    .map((sp) => {
      const x1 = dateToIdx.get(sp.start)
      const x2 = dateToIdx.get(sp.end)
      if (x1 === undefined || x2 === undefined) return null
      return { x1: chartData[x1].date, x2: chartData[x2].date, sp }
    })
    .filter((x): x is NonNullable<typeof x> => x !== null)

  const lostRubColor =
    data.total_lost_revenue >= 100_000 ? 'border-rose-400 bg-rose-50' :
    data.total_lost_revenue >= 10_000  ? 'border-amber-400 bg-amber-50' :
    'border-emerald-300 bg-emerald-50'

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between mb-3 flex-wrap gap-2">
        <div>
          <h2 className="text-lg font-semibold text-fg flex items-center gap-2">
            <Package className="w-4 h-4 text-indigo-600" />
            Остаток → Продажи
          </h2>
          <p className="text-xs text-fg-muted mt-0.5">
            Красные зоны — стокаут (остаток = 0).
            История остатков:{' '}
            <span className="text-fg font-medium tabular-nums">
              {data.history_days_available} дн
            </span>
            {data.earliest_stock_date && (
              <> (с {new Date(data.earliest_stock_date).toLocaleDateString('ru-RU')})</>
            )}
          </p>
        </div>
        <div className="flex gap-1">
          {[28, 30, 90, 180, 365].map((d) => (
            <button key={d} onClick={() => setDays(d)} className={cn(
              'px-2.5 py-1 rounded text-xs border',
              days === d ? 'border-fg bg-fg text-bg'
                : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
            )}>{d}д</button>
          ))}
        </div>
      </div>

      {/* Цена стокаута — главный инсайт */}
      {data.total_stockout_days > 0 ? (
        <div className={cn('rounded-md border-2 p-4 mb-4 flex items-start gap-3', lostRubColor)}>
          <TrendingDown className="w-5 h-5 mt-0.5 shrink-0 text-rose-700" />
          <div className="flex-1">
            <div className="text-sm font-semibold text-fg">
              <span className="tabular-nums">{data.total_stockout_days} дн</span> в стокауте
              {' = '}потеряно ~
              <span className="tabular-nums">{formatNumber(data.total_lost_units)} шт</span>
              {' = '}
              <span className="text-rose-700 tabular-nums">
                ~{formatCurrency(data.total_lost_revenue)}
              </span>
            </div>
            <div className="text-xs text-fg-muted mt-1">
              Оценка по средней скорости продаж до стокаута:{' '}
              <span className="tabular-nums">{data.avg_daily_velocity_units.toFixed(1)} шт/день</span> ×{' '}
              <span className="tabular-nums">{formatCurrency(data.avg_unit_price)}</span>/шт
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-md border border-emerald-300 bg-emerald-50/60 p-3 mb-4 text-sm text-emerald-800 flex items-center gap-2">
          <Package className="w-4 h-4" />
          За период стокаутов не было. Скорость продаж:{' '}
          <span className="tabular-nums font-medium">
            {data.avg_daily_velocity_units.toFixed(1)} шт/день
          </span>
        </div>
      )}

      <div className="h-[280px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} interval="preserveStartEnd" />
            <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#6b7280' }} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: '#10b981' }} />
            <Tooltip
              formatter={(v: number, name) =>
                [formatNumber(v), name === 'stock' ? 'Остаток' : 'Продажи']
              }
            />
            <Legend wrapperStyle={{ fontSize: 11, paddingTop: 4 }}
                    formatter={(v) => (v === 'stock' ? 'Остаток (шт)' : 'Продажи (шт)')} />
            {/* Красные зоны стокаута */}
            {stockoutSpans.map((s, i) => (
              <ReferenceArea
                key={i}
                yAxisId="left"
                x1={s.x1}
                x2={s.x2}
                fill="#fecaca"
                fillOpacity={0.45}
                ifOverflow="visible"
              />
            ))}
            <Line yAxisId="left" type="monotone" dataKey="stock" stroke="#6366f1"
                  strokeWidth={2} dot={false} name="stock" />
            <Bar yAxisId="right" dataKey="sales" fill="#10b981" name="sales" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Список зон стокаута */}
      {data.stockout_periods.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-bg-subtle/40 border-y border-border-subtle">
              <tr className="text-left text-fg-muted uppercase tracking-wider">
                <th className="py-2 px-2.5 font-medium">Период стокаута</th>
                <th className="py-2 px-2.5 font-medium text-right">Дней</th>
                <th className="py-2 px-2.5 font-medium text-right">Потеряно, шт</th>
                <th className="py-2 px-2.5 font-medium text-right">Потеряно, ₽</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {data.stockout_periods.map((sp, i) => (
                <tr key={i} className="hover:bg-bg-subtle/30">
                  <td className="py-1.5 px-2.5 text-fg flex items-center gap-1.5">
                    <AlertTriangle className="w-3 h-3 text-rose-700" />
                    {new Date(sp.start).toLocaleDateString('ru-RU')} … {new Date(sp.end).toLocaleDateString('ru-RU')}
                  </td>
                  <td className="py-1.5 px-2.5 text-right tabular-nums">{sp.days}</td>
                  <td className="py-1.5 px-2.5 text-right tabular-nums">{formatNumber(sp.lost_units_estimate)}</td>
                  <td className="py-1.5 px-2.5 text-right tabular-nums text-rose-700">
                    {formatCurrency(sp.lost_revenue_estimate)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
