/**
 * Матрица метрика × день (nepsell-канон).
 * Выбор метрик галочками, гранулярность (день/неделя/месяц), экспорт CSV.
 */
import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, Download, Grid3x3 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatNumber, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'

interface MetricInfo { key: string; label: string; group: string }
interface MatrixRow { date: string; values: Record<string, number | null> }
interface MatrixResp {
  period_from: string; period_to: string; granularity: string
  metrics: MetricInfo[]; rows: MatrixRow[]
}

const DEFAULT_SELECTED = new Set(['impressions', 'card_visits', 'orders', 'delivered', 'ad_spend'])

export function MetricsMatrix() {
  const { selectedCabinetIds } = useCabinetStore()
  const [days, setDays] = useState(28)
  const [granularity, setGranularity] = useState<'day' | 'week' | 'month'>('day')
  const [selected, setSelected] = useState<Set<string>>(new Set(DEFAULT_SELECTED))

  const { data: available } = useQuery<MetricInfo[]>({
    queryKey: ['metrics', 'available'],
    queryFn: async () => (await api.get('/analytics/metrics-matrix/available')).data,
    staleTime: Infinity,
  })

  const qs = useMemo(() => {
    const p = new URLSearchParams({ days: String(days), granularity })
    selected.forEach((m) => p.append('metrics', m))
    selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
    return p.toString()
  }, [days, granularity, selected, selectedCabinetIds])

  const { data, isLoading } = useQuery<MatrixResp>({
    queryKey: ['metrics-matrix', qs],
    queryFn: async () => (await api.get(`/analytics/metrics-matrix/?${qs}`, { timeout: 60_000 })).data,
  })

  const toggle = (k: string) => setSelected((prev) => {
    const next = new Set(prev)
    next.has(k) ? next.delete(k) : next.add(k)
    return next
  })

  const groups = useMemo(() => {
    if (!available) return {}
    const g: Record<string, MetricInfo[]> = {}
    available.forEach((m) => { (g[m.group] ||= []).push(m) })
    return g
  }, [available])

  const exportCsv = () => {
    if (!data) return
    const headers = ['date', ...data.metrics.map((m) => m.label)]
    const lines = [headers.join(';')]
    for (const r of data.rows) {
      lines.push([r.date, ...data.metrics.map((m) => r.values[m.key] ?? '')].join(';'))
    }
    const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `metrics_matrix_${data.period_from}_${data.period_to}.csv`
    a.click(); URL.revokeObjectURL(url)
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight flex items-center gap-2">
            <Grid3x3 className="w-7 h-7 text-indigo-600" /> Матрица метрик
          </h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Выбери метрики и период — увидишь динамику по дням / неделям / месяцам.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          {[7, 28, 30, 90, 365].map((d) => (
            <button key={d} onClick={() => setDays(d)} className={cn(
              'px-3 py-1.5 rounded-md text-sm border',
              days === d ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle',
            )}>{d === 365 ? 'Год' : `${d}д`}</button>
          ))}
          <span className="border-l border-border-subtle ml-1" />
          {(['day', 'week', 'month'] as const).map((g) => (
            <button key={g} onClick={() => setGranularity(g)} className={cn(
              'px-3 py-1.5 rounded-md text-sm border',
              granularity === g ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle',
            )}>{g === 'day' ? 'Дни' : g === 'week' ? 'Недели' : 'Месяцы'}</button>
          ))}
          <button onClick={exportCsv} disabled={!data}
                  className="px-3 py-1.5 rounded-md text-sm border border-border-subtle text-fg-muted hover:bg-bg-subtle inline-flex items-center gap-1">
            <Download className="w-3.5 h-3.5" /> CSV
          </button>
        </div>
      </div>

      {/* Чекбоксы метрик по группам */}
      <Card className="p-4">
        <div className="text-xs font-semibold text-fg-muted uppercase tracking-wider mb-2">
          Метрики ({selected.size} выбрано из {available?.length ?? 0})
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
          {Object.entries(groups).map(([gName, metrics]) => (
            <div key={gName} className="text-xs">
              <div className="font-semibold text-fg-muted mb-1">{gName}</div>
              {metrics.map((m) => (
                <label key={m.key} className="flex items-center gap-1.5 cursor-pointer py-0.5 hover:bg-bg-subtle rounded px-1">
                  <input type="checkbox" checked={selected.has(m.key)} onChange={() => toggle(m.key)} />
                  <span className="text-fg">{m.label}</span>
                </label>
              ))}
            </div>
          ))}
        </div>
      </Card>

      {/* Таблица */}
      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-fg-muted" /></div>
        ) : !data || data.rows.length === 0 ? (
          <div className="py-12 text-center text-fg-muted text-sm">Нет данных за выбранный период</div>
        ) : (
          <div className="overflow-x-auto max-h-[600px]">
            <table className="w-full text-xs">
              <thead className="bg-bg-subtle/50 border-b border-border-subtle sticky top-0">
                <tr className="text-fg-muted uppercase">
                  <th className="text-left py-2 px-3">{granularity === 'day' ? 'Дата' : granularity === 'week' ? 'Неделя' : 'Месяц'}</th>
                  {data.metrics.map((m) => (
                    <th key={m.key} className="text-right py-2 px-2 whitespace-nowrap">{m.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {data.rows.map((r) => (
                  <tr key={r.date} className="hover:bg-bg-subtle/40">
                    <td className="py-1.5 px-3 font-mono">{r.date}</td>
                    {data.metrics.map((m) => {
                      const v = r.values[m.key]
                      return (
                        <td key={m.key} className="text-right py-1.5 px-2 tabular-nums">
                          {v == null ? '—' : m.key.endsWith('_pct') ? `${v}%` : formatNumber(v)}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
