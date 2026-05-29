import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Target, Plus, Trash2, Loader2, TrendingUp, TrendingDown } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'

interface PVFRow {
  metric: string
  label: string
  target: number
  fact: number
  progress_pct: number
  forecast: number
  forecast_progress_pct: number
  days_passed: number
  days_remaining: number
}

interface TargetRow {
  id: string
  period_from: string
  period_to: string
  metric: string
  target_value: number
  cabinet_id: string | null
  notes: string | null
}

const METRIC_LABELS: Record<string, string> = {
  revenue: 'Выручка',
  gross_profit: 'Валовая прибыль',
  orders: 'Заказы',
  aov: 'Средний чек',
  margin_pct: 'Маржа %',
}

function isMoneyMetric(m: string) {
  return m === 'revenue' || m === 'gross_profit' || m === 'aov'
}

export function PlanVsFact() {
  const qc = useQueryClient()
  const today = new Date()
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().slice(0, 10)
  const lastDay = new Date(today.getFullYear(), today.getMonth() + 1, 0).toISOString().slice(0, 10)

  const [periodFrom, setPeriodFrom] = useState(firstDay)
  const [periodTo, setPeriodTo] = useState(lastDay)

  const { data, isLoading } = useQuery<{ rows: PVFRow[]; period_from: string; period_to: string }>({
    queryKey: ['pvf', periodFrom, periodTo],
    queryFn: async () =>
      (await api.get(`/analytics/plan-vs-fact/?period_from=${periodFrom}&period_to=${periodTo}`)).data,
  })

  const { data: targets } = useQuery<TargetRow[]>({
    queryKey: ['pvf', 'targets'],
    queryFn: async () => (await api.get('/analytics/plan-vs-fact/targets')).data,
  })

  const [showForm, setShowForm] = useState(false)
  const [metric, setMetric] = useState('revenue')
  const [value, setValue] = useState('')

  const create = useMutation({
    mutationFn: async () =>
      (await api.post('/analytics/plan-vs-fact/targets', {
        period_from: periodFrom,
        period_to: periodTo,
        metric,
        target_value: parseFloat(value),
      })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pvf'] })
      setShowForm(false)
      setValue('')
    },
  })

  const del = useMutation({
    mutationFn: async (id: string) => api.delete(`/analytics/plan-vs-fact/targets/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pvf'] }),
  })

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">План / Факт</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          Поставь цели на месяц/квартал — система покажет прогресс и прогноз дотягивания
        </p>
      </div>

      {/* Period */}
      <Card className="p-4 flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">От</label>
          <Input type="date" value={periodFrom} onChange={(e) => setPeriodFrom(e.target.value)} className="w-[150px]" />
        </div>
        <div>
          <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">До</label>
          <Input type="date" value={periodTo} onChange={(e) => setPeriodTo(e.target.value)} className="w-[150px]" />
        </div>
        <Button onClick={() => setShowForm((v) => !v)}>
          <Plus className="w-4 h-4" /> Цель
        </Button>
      </Card>

      {showForm && (
        <Card className="p-5">
          <h3 className="text-base font-semibold text-fg mb-4">Новая цель на период {periodFrom} … {periodTo}</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Метрика</label>
              <select value={metric} onChange={(e) => setMetric(e.target.value)}
                className="h-9 px-3 rounded-md border border-border bg-surface text-sm w-full">
                {Object.entries(METRIC_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Цель</label>
              <Input type="number" value={value} onChange={(e) => setValue(e.target.value)} placeholder="напр. 5000000" />
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="ghost" onClick={() => setShowForm(false)}>Отмена</Button>
            <Button onClick={() => create.mutate()} disabled={create.isPending || !value}>
              {create.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Сохранить'}
            </Button>
          </div>
        </Card>
      )}

      {isLoading ? (
        <Card className="py-16 flex justify-center"><Loader2 className="w-5 h-5 animate-spin" /></Card>
      ) : (data?.rows.length ?? 0) === 0 ? (
        <Card className="py-12 flex flex-col items-center text-fg-muted text-sm">
          <Target className="w-8 h-8 mb-2 text-fg-subtle" />
          <p>Цели на этот период не заданы. Добавьте первую.</p>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {data!.rows.map((r) => {
              const onTrack = r.forecast_progress_pct >= 100
              const fmt = (v: number) =>
                r.metric === 'margin_pct' ? `${v.toFixed(1)}%` :
                isMoneyMetric(r.metric) ? formatCurrency(v) : formatNumber(v)
              return (
                <Card key={r.metric} className="p-5">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-base font-semibold text-fg">{r.label}</h3>
                    {onTrack ? (
                      <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">
                        <TrendingUp className="w-3 h-3" /> по плану
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-amber-50 text-amber-700">
                        <TrendingDown className="w-3 h-3" /> отстаём
                      </span>
                    )}
                  </div>

                  <div className="text-sm text-fg-muted mb-1">
                    Цель: <strong className="text-fg tabular-nums">{fmt(r.target)}</strong>
                  </div>
                  <div className="text-sm text-fg-muted mb-3">
                    Факт: <strong className="text-fg tabular-nums">{fmt(r.fact)}</strong>
                  </div>

                  <div className="relative h-3 rounded-full bg-bg-subtle overflow-hidden mb-1">
                    <div className={cn('h-full rounded-full',
                      r.progress_pct >= 100 ? 'bg-emerald-500' :
                      r.progress_pct >= 75 ? 'bg-emerald-400' :
                      r.progress_pct >= 50 ? 'bg-amber-400' : 'bg-rose-400',
                    )} style={{ width: `${Math.min(100, r.progress_pct)}%` }} />
                  </div>
                  <div className="flex justify-between text-xs text-fg-muted mb-3">
                    <span>{r.progress_pct}% от плана</span>
                    <span>{r.days_passed}/{r.days_passed + r.days_remaining} дн</span>
                  </div>

                  <div className="pt-3 border-t border-border-subtle text-xs">
                    <span className="text-fg-muted">Прогноз на конец периода: </span>
                    <strong className={cn(
                      'tabular-nums',
                      onTrack ? 'text-emerald-700' : 'text-rose-700',
                    )}>{fmt(r.forecast)}</strong>
                    <span className="text-fg-muted"> ({r.forecast_progress_pct}% от плана)</span>
                  </div>
                </Card>
              )
            })}
          </div>

          {(targets?.length ?? 0) > 0 && (
            <Card className="p-4">
              <h3 className="text-sm font-semibold text-fg mb-3">Все цели</h3>
              <ul className="divide-y divide-border-subtle text-sm">
                {targets!.map((t) => (
                  <li key={t.id} className="py-2 flex items-center gap-3">
                    <span className="text-fg-muted text-xs tabular-nums">{t.period_from} … {t.period_to}</span>
                    <span className="text-fg font-medium">{METRIC_LABELS[t.metric] || t.metric}</span>
                    <span className="text-fg-muted ml-auto tabular-nums">
                      {isMoneyMetric(t.metric) ? formatCurrency(t.target_value) :
                       t.metric === 'margin_pct' ? `${t.target_value}%` : formatNumber(t.target_value)}
                    </span>
                    <button onClick={() => del.mutate(t.id)} className="p-1 text-fg-subtle hover:text-rose-700">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
