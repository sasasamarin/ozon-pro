/**
 * Custom X/Y чарт-builder — юзер сам строит график.
 * Выбор: X-метрика, Y1-метрика, Y2-метрика, тип графика, период.
 * Использует /api/v1/analytics/metrics-matrix для данных.
 */
import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sliders, Loader2 } from 'lucide-react'
import {
  ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ScatterChart, Scatter,
} from 'recharts'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatNumber, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'

interface MetricInfo { key: string; label: string; group: string }
interface MatrixRow { date: string; values: Record<string, number | null> }
interface MatrixResp { metrics: MetricInfo[]; rows: MatrixRow[] }

type ChartType = 'line' | 'bar' | 'scatter'

export function MetricsBuilder() {
  const { selectedCabinetIds } = useCabinetStore()
  const [days, setDays] = useState(28)
  const [chartType, setChartType] = useState<ChartType>('line')
  const [xMetric, setXMetric] = useState<string>('date')     // 'date' = ось времени
  const [yMetrics, setYMetrics] = useState<string[]>(['impressions', 'orders'])

  const { data: available } = useQuery<MetricInfo[]>({
    queryKey: ['metrics', 'available'],
    queryFn: async () => (await api.get('/analytics/metrics-matrix/available')).data,
    staleTime: Infinity,
  })

  const qs = useMemo(() => {
    const p = new URLSearchParams({ days: String(days) })
    yMetrics.forEach((m) => p.append('metrics', m))
    if (xMetric !== 'date') p.append('metrics', xMetric)
    selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
    return p.toString()
  }, [days, xMetric, yMetrics, selectedCabinetIds])

  const { data, isLoading } = useQuery<MatrixResp>({
    queryKey: ['metrics-builder', qs],
    queryFn: async () => (await api.get(`/analytics/metrics-matrix/?${qs}`, { timeout: 60_000 })).data,
  })

  const chartData = useMemo(() => {
    if (!data) return []
    return data.rows.map((r) => ({
      date: r.date,
      ...r.values,
    }))
  }, [data])

  const colors = ['#2563eb', '#dc2626', '#10b981', '#f59e0b', '#a855f7']

  const yLabels: Record<string, string> = {}
  data?.metrics.forEach((m) => { yLabels[m.key] = m.label })

  const renderChart = () => {
    if (chartType === 'scatter') {
      const xKey = xMetric === 'date' ? 'impressions' : xMetric
      const yKey = yMetrics[0] || 'orders'
      return (
        <ScatterChart>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis type="number" dataKey={xKey} name={yLabels[xKey] || xKey}
                 tick={{ fontSize: 11, fill: '#6b7280' }}
                 tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : `${v}`} />
          <YAxis type="number" dataKey={yKey} name={yLabels[yKey] || yKey}
                 tick={{ fontSize: 11, fill: '#6b7280' }} />
          <Tooltip cursor={{ strokeDasharray: '3 3' }}
                   formatter={(v: number, name: string) => [formatNumber(v), yLabels[name] || name]} />
          <Scatter data={chartData} fill="#6366f1" />
        </ScatterChart>
      )
    }
    return (
      <ComposedChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#6b7280' }} />
        <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#6b7280' }}
               tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : `${v}`} />
        {yMetrics.length > 1 && (
          <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: '#6b7280' }} />
        )}
        <Tooltip formatter={(v: number, name: string) => [formatNumber(v), yLabels[name] || name]} />
        <Legend wrapperStyle={{ fontSize: 12 }}
                formatter={(v: string) => yLabels[v] || v} />
        {yMetrics.map((m, i) => chartType === 'bar' ? (
          <Bar key={m} yAxisId={i === 0 ? 'left' : 'right'} dataKey={m} fill={colors[i % colors.length]} />
        ) : (
          <Line key={m} yAxisId={i === 0 ? 'left' : 'right'} type="monotone" dataKey={m}
                stroke={colors[i % colors.length]} strokeWidth={2} dot={false} />
        ))}
      </ComposedChart>
    )
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight flex items-center gap-2">
            <Sliders className="w-7 h-7 text-purple-600" /> Конструктор графиков
          </h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Строй собственные графики: ось X, ось Y, наложи несколько метрик. Найди взаимосвязи.
          </p>
        </div>
        <div className="flex gap-2">
          {[7, 28, 30, 90].map((d) => (
            <button key={d} onClick={() => setDays(d)} className={cn(
              'px-3 py-1.5 rounded-md text-sm border',
              days === d ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle',
            )}>{d}д</button>
          ))}
        </div>
      </div>

      {/* Настройки графика */}
      <Card className="p-4 space-y-3">
        <div className="flex items-center gap-2 text-xs">
          <span className="font-semibold text-fg-muted uppercase tracking-wider">Тип графика:</span>
          {(['line', 'bar', 'scatter'] as const).map((t) => (
            <button key={t} onClick={() => setChartType(t)} className={cn(
              'px-3 py-1 rounded text-sm border',
              chartType === t ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle',
            )}>
              {t === 'line' ? 'Линия' : t === 'bar' ? 'Бары' : 'Scatter (X×Y точки)'}
            </button>
          ))}
        </div>

        {chartType === 'scatter' && (
          <div className="flex items-center gap-2 text-xs">
            <span className="font-semibold text-fg-muted uppercase tracking-wider">Ось X:</span>
            <select value={xMetric} onChange={(e) => setXMetric(e.target.value)}
                    className="px-2 py-1 rounded border border-border-subtle bg-bg">
              {available?.map((m) => (
                <option key={m.key} value={m.key}>{m.group}: {m.label}</option>
              ))}
            </select>
          </div>
        )}

        <div className="text-xs">
          <span className="font-semibold text-fg-muted uppercase tracking-wider">Y-метрики (макс 5):</span>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-1.5 mt-2">
            {available?.map((m) => {
              const checked = yMetrics.includes(m.key)
              const colorIdx = yMetrics.indexOf(m.key)
              return (
                <label key={m.key} className="flex items-center gap-1.5 cursor-pointer py-0.5 px-1 hover:bg-bg-subtle rounded">
                  <input type="checkbox" checked={checked} onChange={() => {
                    if (checked) setYMetrics(yMetrics.filter((x) => x !== m.key))
                    else if (yMetrics.length < 5) setYMetrics([...yMetrics, m.key])
                  }} />
                  {checked && (
                    <span className="w-2 h-2 rounded-full shrink-0"
                          style={{ background: colors[colorIdx % colors.length] }} />
                  )}
                  <span className="text-fg text-[11px]">{m.label}</span>
                  <span className="text-[10px] text-fg-subtle">{m.group}</span>
                </label>
              )
            })}
          </div>
        </div>
      </Card>

      {/* График */}
      <Card className="p-4">
        {isLoading || !data ? (
          <div className="h-[400px] flex justify-center items-center text-fg-muted">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : (
          <div className="h-[420px]">
            <ResponsiveContainer width="100%" height="100%">{renderChart()}</ResponsiveContainer>
          </div>
        )}
      </Card>
    </div>
  )
}
