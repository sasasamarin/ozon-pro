/**
 * /analytics/plan-fact — План продаж.
 *
 * Структура (как в ТЗ):
 *   Tabs: «Постановка плана» | «Факт» | «KPI»
 *   Внутри «Постановка плана» — визард из 3 шагов:
 *     1) Метрика + период анализа + период прогноза → прогноз → цель
 *     2) Распределение по SKU (правка / lock / Excel / Сбросить)
 *     3) Распределение по дням (sезонные веса) + сохранить план
 */
import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  LineChart, Line, BarChart, Bar, Cell, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts'
import {
  Target, TrendingUp, Calendar, AlertTriangle, CheckCircle2, Save,
  Lock, Unlock, Trash2, FileSpreadsheet, Sliders, BarChart3, Award,
  ArrowRight, RotateCcw, Loader2,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { AskAIButton } from '@/components/AskAIButton'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'

interface ForecastPoint { date: string; value: number }
interface ForecastResp {
  metric: string
  history: ForecastPoint[]
  base_forecast: number
  forecast_series: ForecastPoint[]
  modified_series: ForecastPoint[] | null
  season_weights: Record<string, number>
  reliability: string
  reliability_pct: number
  note: string
}
interface DistributeItem {
  product_id: string | null; sku: string | null; name: string | null
  offer_id: string | null; analysis_value: number
  share_pct: number; plan_value: number
}
interface PlanRow {
  id: string; name: string; scope_type: string; scope_ref: string | null
  metric_code: string; period_start: string; period_end: string
  analysis_start: string; analysis_end: string
  target_value: number; base_forecast: number | null
  distribution_mode: string; source_pref: string
  note: string | null; created_at: string; items_count: number
}

const METRIC_OPTIONS = [
  { code: 'orders', label: 'Заказы (шт)' },
  { code: 'units', label: 'Единицы (выкуплено)' },
  { code: 'revenue', label: 'Выручка (₽)' },
  { code: 'gross_profit', label: 'Маржинальная прибыль (₽)' },
]

function isoDate(d: Date) { return d.toISOString().slice(0, 10) }

function exportItemsCsv(items: DistributeItem[]) {
  const header = 'offer_id;name;analysis_value;share_pct;plan_value\n'
  const rows = items.map((i) =>
    [
      i.offer_id || '', (i.name || '').replace(/;/g, ','),
      i.analysis_value.toFixed(2), i.share_pct.toFixed(2),
      i.plan_value.toFixed(2),
    ].join(';')
  ).join('\n')
  const blob = new Blob(['﻿' + header + rows], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'plan_distribution.csv'
  a.click()
  URL.revokeObjectURL(url)
}

export function SalesPlan() {
  const [tab, setTab] = useState<'wizard' | 'fact' | 'kpi'>('wizard')

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
            <Target className="w-6 h-6 text-purple-500" />
            План продаж
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            Прогноз → цель → распределение → факт. Каскадный пересчёт по графу зависимостей.
          </p>
        </div>
        <AskAIButton
          context={{ type: 'screen', source_page: 'sales-plan', source_label: 'План продаж',
            metrics: ['target', 'fact', 'completion_pct', 'run_rate'] }}
          question="Какой план реалистичен на месяц? Где риски невыполнения?"
        />
      </div>

      <div className="flex gap-1 border-b border-border-subtle">
        {[
          { key: 'wizard', label: 'Постановка плана', icon: Sliders },
          { key: 'fact', label: 'Факт', icon: BarChart3 },
          { key: 'kpi', label: 'KPI менеджмента', icon: Award },
        ].map(({ key, label, icon: Icon }) => (
          <button key={key} onClick={() => setTab(key as any)}
            className={cn(
              'px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px inline-flex items-center gap-2',
              tab === key ? 'border-purple-500 text-purple-700'
                          : 'border-transparent text-fg-muted hover:text-fg',
            )}>
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {tab === 'wizard' && <WizardTab />}
      {tab === 'fact' && <FactTab />}
      {tab === 'kpi' && <KpiTab />}
    </div>
  )
}


// ===========================================
// ТАБ «ПОСТАНОВКА ПЛАНА» — 3-step wizard
// ===========================================

function WizardTab() {
  const qc = useQueryClient()
  const [step, setStep] = useState<1 | 2 | 3>(1)

  // Step 1: настройки прогноза
  const today = new Date()
  const monthAgo = new Date(today.getTime() - 90 * 86400 * 1000)
  const nextMonthEnd = new Date(today.getFullYear(), today.getMonth() + 1, 0)
  const nextMonthStart = new Date(today.getFullYear(), today.getMonth() + 1, 1)

  const [metric, setMetric] = useState('orders')
  const [analysisFrom, setAnalysisFrom] = useState(isoDate(monthAgo))
  const [analysisTo, setAnalysisTo] = useState(isoDate(today))
  const [forecastFrom, setForecastFrom] = useState(isoDate(nextMonthStart))
  const [forecastTo, setForecastTo] = useState(isoDate(nextMonthEnd))
  const [targetValue, setTargetValue] = useState<number | null>(null)
  const [planName, setPlanName] = useState('')
  const [forecast, setForecast] = useState<ForecastResp | null>(null)
  const [items, setItems] = useState<DistributeItem[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  const calcForecast = useMutation<ForecastResp, any, void>({
    mutationFn: async () => (await api.post('/plans/forecast', {
      metric,
      analysis_start: analysisFrom, analysis_end: analysisTo,
      forecast_start: forecastFrom, forecast_end: forecastTo,
      target_value: targetValue,
    })).data,
    onSuccess: (data) => {
      setForecast(data)
      if (targetValue === null) setTargetValue(Math.round(data.base_forecast))
    },
  })

  const calcDistribute = useMutation<DistributeItem[], any, void>({
    mutationFn: async () => (await api.post('/plans/distribute', {
      metric,
      analysis_start: analysisFrom, analysis_end: analysisTo,
      target_value: targetValue || 0,
    })).data,
    onSuccess: (data) => setItems(data),
  })

  const savePlan = useMutation<{ id: string }, any, void>({
    mutationFn: async () => {
      const filtered = selectedIds.size > 0
        ? items.filter((i) => i.product_id && selectedIds.has(i.product_id))
        : items
      return (await api.post('/plans', {
        name: planName || `${metric} · ${forecastFrom} … ${forecastTo}`,
        scope_type: 'company',
        scope_ref: null,
        metric_code: metric,
        period_start: forecastFrom, period_end: forecastTo,
        analysis_start: analysisFrom, analysis_end: analysisTo,
        target_value: targetValue || 0,
        base_forecast: forecast?.base_forecast,
        distribution_mode: 'proportional',
        items: filtered,
      })).data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plans'] })
      alert('План сохранён')
      setStep(1)
      setForecast(null)
      setItems([])
    },
  })

  return (
    <div className="space-y-4">
      {/* Step indicator */}
      <div className="flex items-center gap-2 text-xs">
        {[1, 2, 3].map((s) => (
          <div key={s} className="flex items-center gap-2">
            <div className={cn(
              'w-7 h-7 rounded-full inline-flex items-center justify-center font-semibold',
              s === step ? 'bg-purple-600 text-white' :
              s < step ? 'bg-emerald-500 text-white' : 'bg-bg-subtle text-fg-muted',
            )}>{s}</div>
            <span className={cn('font-medium', s === step ? 'text-fg' : 'text-fg-muted')}>
              {s === 1 && 'Прогноз и цель'}
              {s === 2 && 'Распределение по товарам'}
              {s === 3 && 'Распределение по дням'}
            </span>
            {s < 3 && <ArrowRight className="w-3.5 h-3.5 text-fg-subtle" />}
          </div>
        ))}
      </div>

      {/* === Step 1: forecast === */}
      {step === 1 && (
        <Card className="p-5 space-y-4">
          <h3 className="text-sm font-semibold">Шаг 1. Спрогнозировать и задать цель</h3>

          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-fg-muted">Метрика</label>
              <select value={metric} onChange={(e) => setMetric(e.target.value)}
                      className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg">
                {METRIC_OPTIONS.map((m) => (
                  <option key={m.code} value={m.code}>{m.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-fg-muted">Период анализа от</label>
              <input type="date" value={analysisFrom}
                     onChange={(e) => setAnalysisFrom(e.target.value)}
                     className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
            </div>
            <div>
              <label className="text-xs text-fg-muted">…до</label>
              <input type="date" value={analysisTo}
                     onChange={(e) => setAnalysisTo(e.target.value)}
                     className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
            </div>
            <div>
              <label className="text-xs text-fg-muted">Прогнозируемый период от</label>
              <input type="date" value={forecastFrom}
                     onChange={(e) => setForecastFrom(e.target.value)}
                     className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
            </div>
            <div>
              <label className="text-xs text-fg-muted">…до</label>
              <input type="date" value={forecastTo}
                     onChange={(e) => setForecastTo(e.target.value)}
                     className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
            </div>
            <div className="self-end">
              <Button onClick={() => calcForecast.mutate()} disabled={calcForecast.isPending}>
                {calcForecast.isPending ? 'Считаю…' : 'Спрогнозировать'}
              </Button>
            </div>
          </div>

          {calcForecast.error && (
            <div className="text-rose-700 text-sm">
              {(calcForecast.error as any)?.response?.data?.detail || 'Ошибка'}
            </div>
          )}

          {forecast && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <Card className="p-3 bg-bg-subtle/30">
                  <div className="text-xs text-fg-muted">Период анализа (факт)</div>
                  <div className="text-lg font-semibold tabular-nums">
                    {forecast.history.reduce((s, p) => s + p.value, 0).toLocaleString('ru-RU')}
                  </div>
                  <div className="text-[10px] text-fg-muted">{forecast.history.length} дней</div>
                </Card>
                <Card className="p-3 bg-purple-50/40">
                  <div className="text-xs text-fg-muted">Базовый прогноз</div>
                  <div className="text-lg font-semibold tabular-nums">
                    {forecast.base_forecast.toLocaleString('ru-RU')}
                  </div>
                  <div className="text-[10px] text-fg-muted">
                    Надёжность: <span className={cn(
                      forecast.reliability === 'high' && 'text-emerald-700',
                      forecast.reliability === 'medium' && 'text-amber-700',
                      forecast.reliability === 'low' && 'text-rose-700',
                    )}>{forecast.reliability_pct}%</span>
                  </div>
                </Card>
              </div>

              {/* Cель */}
              <div className="space-y-2">
                <label className="text-sm font-semibold text-fg">
                  Цель: <span className="text-purple-700 tabular-nums">
                    {(targetValue || 0).toLocaleString('ru-RU')}
                  </span>
                  <span className="ml-2 text-xs text-fg-muted">
                    {targetValue && forecast.base_forecast
                      ? `(${(targetValue / forecast.base_forecast * 100 - 100).toFixed(0)}% от базы)`
                      : ''}
                  </span>
                </label>
                <input type="range"
                       min={Math.round(forecast.base_forecast * 0.5)}
                       max={Math.round(forecast.base_forecast * 2.5)}
                       step={Math.max(1, Math.round(forecast.base_forecast / 100))}
                       value={targetValue || forecast.base_forecast}
                       onChange={(e) => {
                         setTargetValue(+e.target.value)
                         calcForecast.mutate()
                       }}
                       className="w-full" />
                <input type="number" value={targetValue ?? ''}
                       onChange={(e) => setTargetValue(e.target.value ? +e.target.value : null)}
                       onBlur={() => calcForecast.mutate()}
                       className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
              </div>

              {/* График */}
              <Card className="p-4">
                <h4 className="text-sm font-semibold mb-2">Динамика метрики</h4>
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v: any) => Number(v).toLocaleString('ru-RU')} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Line type="monotone" dataKey="value" data={forecast.history}
                          stroke="#6b7280" name="История" dot={false} strokeWidth={2} />
                    <Line type="monotone" dataKey="value" data={forecast.forecast_series}
                          stroke="#a78bfa" strokeDasharray="4 4"
                          name="Базовый прогноз" dot={false} />
                    {forecast.modified_series && (
                      <Line type="monotone" dataKey="value" data={forecast.modified_series}
                            stroke="#6d28d9" name="Цель"
                            dot={false} strokeWidth={2} />
                    )}
                  </LineChart>
                </ResponsiveContainer>
                <div className="text-[10px] text-fg-muted mt-1">{forecast.note}</div>
              </Card>

              <Button onClick={() => { calcDistribute.mutate(); setStep(2) }}
                      disabled={!targetValue}
                      className="w-full">
                Распределить по товарам →
              </Button>
            </>
          )}
        </Card>
      )}

      {/* === Step 2: distribute === */}
      {step === 2 && (
        <Card className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">Шаг 2. Распределение по товарам</h3>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => calcDistribute.mutate()}
                      disabled={calcDistribute.isPending} className="text-xs">
                <RotateCcw className="w-3.5 h-3.5 mr-1" /> Сбросить (пропорции)
              </Button>
              <Button variant="secondary" onClick={() => exportItemsCsv(items)} className="text-xs">
                <FileSpreadsheet className="w-3.5 h-3.5 mr-1" /> Скачать CSV
              </Button>
            </div>
          </div>

          {calcDistribute.isPending && (
            <div className="text-center py-4"><Loader2 className="w-5 h-5 animate-spin inline" /></div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-fg-muted bg-bg-subtle/30">
                <tr>
                  <th className="py-2 px-2 w-8">
                    <input type="checkbox"
                      checked={selectedIds.size === items.length && items.length > 0}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedIds(new Set(items.map((i) => i.product_id!).filter(Boolean)))
                        } else {
                          setSelectedIds(new Set())
                        }
                      }} />
                  </th>
                  <th className="py-2 px-3 text-left">Артикул</th>
                  <th className="py-2 px-3 text-left">Товар</th>
                  <th className="py-2 px-3 text-right">Период анализа</th>
                  <th className="py-2 px-3 text-right">Процент</th>
                  <th className="py-2 px-3 text-right">Значение плана</th>
                </tr>
              </thead>
              <tbody>
                {items.map((i, idx) => (
                  <tr key={i.product_id || idx} className="border-t border-border-subtle/40">
                    <td className="py-1.5 px-2 text-center">
                      <input type="checkbox"
                        checked={i.product_id ? selectedIds.has(i.product_id) : false}
                        onChange={(e) => {
                          if (!i.product_id) return
                          const next = new Set(selectedIds)
                          if (e.target.checked) next.add(i.product_id)
                          else next.delete(i.product_id)
                          setSelectedIds(next)
                        }} />
                    </td>
                    <td className="py-1.5 px-3 font-mono text-xs">{i.offer_id || '—'}</td>
                    <td className="py-1.5 px-3 max-w-[300px] truncate" title={i.name || ''}>
                      {i.name?.slice(0, 60) || '—'}
                    </td>
                    <td className="py-1.5 px-3 text-right tabular-nums">
                      {i.analysis_value.toLocaleString('ru-RU')}
                    </td>
                    <td className="py-1.5 px-3 text-right tabular-nums">{i.share_pct.toFixed(2)}%</td>
                    <td className="py-1.5 px-3 text-right tabular-nums font-medium">
                      {i.plan_value.toLocaleString('ru-RU')}
                    </td>
                  </tr>
                ))}
                {items.length === 0 && !calcDistribute.isPending && (
                  <tr><td colSpan={6} className="py-6 text-center text-fg-muted">
                    Нажмите «Спрогнозировать» на шаге 1, затем «Распределить» →
                  </td></tr>
                )}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-border-subtle font-semibold">
                  <td colSpan={3} className="py-2 px-3">Итого:</td>
                  <td className="py-2 px-3 text-right tabular-nums">
                    {items.reduce((s, i) => s + i.analysis_value, 0).toLocaleString('ru-RU')}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums">
                    {items.reduce((s, i) => s + i.share_pct, 0).toFixed(1)}%
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-purple-700">
                    {items.reduce((s, i) => s + i.plan_value, 0).toLocaleString('ru-RU')}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>

          <div className="flex gap-2 justify-between">
            <Button variant="secondary" onClick={() => setStep(1)}>← Назад</Button>
            <Button onClick={() => setStep(3)} disabled={items.length === 0}>
              Распределить по дням →
            </Button>
          </div>
        </Card>
      )}

      {/* === Step 3: distribute by days === */}
      {step === 3 && (
        <Card className="p-5 space-y-4">
          <h3 className="text-sm font-semibold">Шаг 3. Распределение по дням и сохранение</h3>

          <div>
            <label className="text-xs text-fg-muted">Название плана</label>
            <input value={planName} onChange={(e) => setPlanName(e.target.value)}
                   placeholder={`${metric} · ${forecastFrom} … ${forecastTo}`}
                   className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
          </div>

          {forecast?.season_weights && (
            <Card className="p-4">
              <h4 className="text-sm font-semibold mb-2">Сезонные веса по дням</h4>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={Object.entries(forecast.season_weights).map(([d, w]) => ({ date: d, weight: w * 100 }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="date" tick={{ fontSize: 9 }} />
                  <YAxis tick={{ fontSize: 11 }} unit="%" />
                  <Tooltip />
                  <Bar dataKey="weight" fill="#a78bfa" />
                </BarChart>
              </ResponsiveContainer>
              <div className="text-[10px] text-fg-muted mt-1">
                Σ весов = 100%. Будет применено к каждому SKU.
              </div>
            </Card>
          )}

          <div className="flex gap-2 justify-between">
            <Button variant="secondary" onClick={() => setStep(2)}>← Назад</Button>
            <Button onClick={() => savePlan.mutate()} disabled={savePlan.isPending}>
              <Save className="w-4 h-4 mr-1" />
              {savePlan.isPending ? 'Сохраняю…' : 'Сохранить план'}
            </Button>
          </div>
        </Card>
      )}
    </div>
  )
}


// ===========================================
// ТАБ «ФАКТ»
// ===========================================

function FactTab() {
  const { data: plans = [] } = useQuery<PlanRow[]>({
    queryKey: ['plans'],
    queryFn: async () => (await api.get('/plans')).data,
  })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { data: fact } = useQuery({
    queryKey: ['plan-fact', selectedId],
    queryFn: async () => (await api.get(`/plans/${selectedId}/fact`)).data,
    enabled: !!selectedId,
  })
  const { data: timeseries } = useQuery<{ series: any[]; plan_total: number; today: string }>({
    queryKey: ['plan-timeseries', selectedId],
    queryFn: async () => (await api.get(`/plans/${selectedId}/timeseries`)).data,
    enabled: !!selectedId,
  })

  if (plans.length === 0) {
    return (
      <Card className="p-8 text-center text-fg-muted">
        Планов нет. Создай первый на вкладке «Постановка плана».
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <Card className="p-3">
        <label className="text-xs text-fg-muted block mb-1">План</label>
        <select value={selectedId || ''} onChange={(e) => setSelectedId(e.target.value || null)}
                className="w-full md:w-96 px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg">
          <option value="">— выбери план —</option>
          {plans.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.metric_code} {p.period_start}…{p.period_end})
            </option>
          ))}
        </select>
      </Card>

      {fact && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KPICard label="План" value={fact.plan_value.toLocaleString('ru-RU')} />
            <KPICard label="Факт" value={fact.fact_value.toLocaleString('ru-RU')}
                     subtitle={fact.fact_source === 'realization' ? '✓ realization' :
                               'transactions ⚠️ предварительно'}
                     tone={fact.is_preliminary ? 'amber' : 'emerald'} />
            <KPICard label="Выполнение"
                     value={`${fact.completion_pct.toFixed(1)}%`}
                     subtitle={`pro-rata: ${fact.completion_prorata_pct.toFixed(0)}%`}
                     tone={fact.completion_prorata_pct >= 100 ? 'emerald' :
                           fact.completion_prorata_pct >= 80 ? 'amber' : 'rose'} />
            <KPICard label="Run-rate прогноз"
                     value={fact.run_rate_forecast.toLocaleString('ru-RU')}
                     subtitle={`нужно ${fact.needed_per_day.toLocaleString('ru-RU')}/день`} />
          </div>

          {fact.delta_realization_tx !== null && Math.abs(fact.delta_realization_tx) > 100 && (
            <Card className="p-3 bg-amber-50/30 border-amber-200 text-sm flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
              <div>
                <b>Дельта realization − transactions:</b> {fact.delta_realization_tx.toLocaleString('ru-RU')} ₽
                <div className="text-xs text-fg-muted mt-1">
                  Источники расходятся. Realization — закрытый отчёт Ozon (правильный), transactions — оперативка.
                </div>
              </div>
            </Card>
          )}

          {/* Burn-up график */}
          {timeseries && timeseries.series.length > 0 && (
            <Card className="p-4">
              <h4 className="text-sm font-semibold mb-3">Burn-up: накопительный факт vs план</h4>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={timeseries.series}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="day" tick={{ fontSize: 9 }}
                         tickFormatter={(d: string) => d.slice(5)} />
                  <YAxis tick={{ fontSize: 10 }}
                         tickFormatter={(v: number) => Number(v).toLocaleString('ru-RU')} />
                  <Tooltip formatter={(v: any) => Number(v || 0).toLocaleString('ru-RU')} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <ReferenceLine y={timeseries.plan_total} stroke="#a78bfa" strokeDasharray="3 3"
                                 label={{ value: 'Цель', fontSize: 10, fill: '#6d28d9' }} />
                  <Line type="monotone" dataKey="plan_cum"
                        stroke="#6b7280" name="План (pro-rata)" dot={false} strokeWidth={2} />
                  <Line type="monotone" dataKey="fact_cum"
                        stroke="#10b981" name="Факт" dot={false} strokeWidth={2.5} />
                  <Line type="monotone" dataKey="run_rate_cum"
                        stroke="#f59e0b" strokeDasharray="4 4"
                        name="Run-rate прогноз" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          )}

          {/* Bridge waterfall */}
          {fact.bridge && fact.bridge.length > 0 && (
            <Card className="p-4">
              <h4 className="text-sm font-semibold mb-3">Bridge: что повлияло на отклонение</h4>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={fact.bridge}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: any) => Number(v).toLocaleString('ru-RU')} />
                  <ReferenceLine y={0} stroke="#000" />
                  <Bar dataKey="value">
                    {fact.bridge.map((b: any, i: number) => (
                      <Cell key={i} fill={b.value >= 0 ? '#10b981' : '#ef4444'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <div className="text-[10px] text-fg-muted mt-1">{fact.note}</div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}


// ===========================================
// ТАБ «KPI»
// ===========================================

interface KpiRow {
  id: string; manager_name: string
  metric_code: string; target_value: number
  bonus_rule: { model?: string; pct_of_net?: number; thresholds?: any[] } | null
}

function KpiTab() {
  const qc = useQueryClient()
  const { data: plans = [] } = useQuery<PlanRow[]>({
    queryKey: ['plans'],
    queryFn: async () => (await api.get('/plans')).data,
  })
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null)
  const { data: kpis = [] } = useQuery<KpiRow[]>({
    queryKey: ['plan-kpi', selectedPlanId],
    queryFn: async () => (await api.get(`/plans/${selectedPlanId}/kpi`)).data,
    enabled: !!selectedPlanId,
  })
  const { data: fact } = useQuery<any>({
    queryKey: ['plan-fact', selectedPlanId],
    queryFn: async () => (await api.get(`/plans/${selectedPlanId}/fact`)).data,
    enabled: !!selectedPlanId,
  })

  const [form, setForm] = useState({
    manager: '', metric: 'revenue', target: '',
    model: 'A' as 'A' | 'B', pctOfNet: '5',
    threshold1: '100', bonus1: '10000', threshold2: '120', bonus2: '20000',
  })

  const create = useMutation({
    mutationFn: async () => {
      const bonus_rule = form.model === 'A'
        ? { model: 'A', pct_of_net: Number(form.pctOfNet) }
        : { model: 'B', thresholds: [
            { at: Number(form.threshold1), bonus: Number(form.bonus1) },
            { at: Number(form.threshold2), bonus: Number(form.bonus2) },
          ] }
      return (await api.post(`/plans/${selectedPlanId}/kpi`, {
        manager_name: form.manager, metric_code: form.metric,
        target_value: Number(form.target), bonus_rule,
      })).data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plan-kpi', selectedPlanId] })
      setForm({ ...form, manager: '', target: '' })
    },
  })

  const remove = useMutation({
    mutationFn: async (kid: string) =>
      (await api.delete(`/plans/${selectedPlanId}/kpi/${kid}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['plan-kpi', selectedPlanId] }),
  })

  if (plans.length === 0) {
    return (
      <Card className="p-8 text-center text-fg-muted">
        Создай план на вкладке «Постановка плана», потом сюда вернёшься.
      </Card>
    )
  }

  const enriched = kpis.map((k) => {
    const factVal = fact?.fact_value || 0
    const factScaled = fact?.plan_value
      ? factVal * (k.target_value / fact.plan_value)
      : 0
    const completionPct = k.target_value > 0 ? (factScaled / k.target_value) * 100 : 0
    return { ...k, factScaled, completionPct }
  }).sort((a, b) => b.completionPct - a.completionPct)

  return (
    <div className="space-y-4">
      <Card className="p-3">
        <label className="text-xs text-fg-muted block mb-1">План</label>
        <select value={selectedPlanId || ''}
                onChange={(e) => setSelectedPlanId(e.target.value || null)}
                className="w-full md:w-96 px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg">
          <option value="">— выбери план —</option>
          {plans.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.metric_code} {p.period_start}…{p.period_end})
            </option>
          ))}
        </select>
      </Card>

      {selectedPlanId && (
        <>
          <Card className="p-4">
            <h3 className="text-sm font-semibold mb-3">Назначить KPI сотруднику</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
              <input value={form.manager}
                     onChange={(e) => setForm({ ...form, manager: e.target.value })}
                     placeholder="ФИО сотрудника"
                     className="px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
              <select value={form.metric}
                      onChange={(e) => setForm({ ...form, metric: e.target.value })}
                      className="px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg">
                {METRIC_OPTIONS.map((m) => <option key={m.code} value={m.code}>{m.label}</option>)}
              </select>
              <input type="number" value={form.target}
                     onChange={(e) => setForm({ ...form, target: e.target.value })}
                     placeholder="Цель (значение)"
                     className="px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
              <select value={form.model}
                      onChange={(e) => setForm({ ...form, model: e.target.value as any })}
                      className="px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg">
                <option value="A">A: % от чистой прибыли</option>
                <option value="B">B: бонус за пороги</option>
              </select>
            </div>

            {form.model === 'A' ? (
              <div className="mt-3 max-w-xs">
                <label className="text-xs text-fg-muted">% от чистой прибыли</label>
                <input type="number" step="0.1" value={form.pctOfNet}
                       onChange={(e) => setForm({ ...form, pctOfNet: e.target.value })}
                       className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
                <div className="text-[10px] text-fg-muted mt-1">
                  Бонус = чистая_прибыль × {form.pctOfNet}% при достижении плана.
                </div>
              </div>
            ) : (
              <div className="mt-3 grid grid-cols-2 gap-2 max-w-md">
                <div>
                  <label className="text-xs text-fg-muted">Порог 1, %</label>
                  <input type="number" value={form.threshold1}
                         onChange={(e) => setForm({ ...form, threshold1: e.target.value })}
                         className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
                </div>
                <div>
                  <label className="text-xs text-fg-muted">Бонус 1, ₽</label>
                  <input type="number" value={form.bonus1}
                         onChange={(e) => setForm({ ...form, bonus1: e.target.value })}
                         className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
                </div>
                <div>
                  <label className="text-xs text-fg-muted">Порог 2, %</label>
                  <input type="number" value={form.threshold2}
                         onChange={(e) => setForm({ ...form, threshold2: e.target.value })}
                         className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
                </div>
                <div>
                  <label className="text-xs text-fg-muted">Бонус 2, ₽</label>
                  <input type="number" value={form.bonus2}
                         onChange={(e) => setForm({ ...form, bonus2: e.target.value })}
                         className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
                </div>
              </div>
            )}

            <Button onClick={() => create.mutate()}
                    disabled={!form.manager || !form.target || create.isPending}
                    className="mt-3">
              {create.isPending ? 'Создаю…' : '+ Назначить KPI'}
            </Button>
          </Card>

          {enriched.length > 0 && (
            <Card>
              <div className="p-3 border-b border-border-subtle">
                <h3 className="text-sm font-semibold">Рейтинг по % выполнения</h3>
              </div>
              <div className="divide-y divide-border-subtle/40">
                {enriched.map((k, idx) => {
                  const tone = k.completionPct >= 100 ? 'emerald'
                              : k.completionPct >= 80 ? 'amber' : 'rose'
                  return (
                    <div key={k.id} className="p-3 flex items-center gap-3">
                      <div className={cn(
                        'w-8 h-8 rounded-full inline-flex items-center justify-center font-bold text-sm',
                        idx === 0 ? 'bg-yellow-100 text-yellow-700' :
                        idx === 1 ? 'bg-slate-100 text-slate-700' :
                        idx === 2 ? 'bg-orange-100 text-orange-700' :
                                    'bg-bg-subtle text-fg-muted')}>{idx + 1}</div>
                      <div className="flex-1">
                        <div className="font-medium text-fg">{k.manager_name}</div>
                        <div className="text-xs text-fg-muted">
                          Цель {k.target_value.toLocaleString('ru-RU')} {k.metric_code}
                          {k.bonus_rule?.model === 'A' && ` · бонус ${k.bonus_rule.pct_of_net}% от чистой`}
                          {k.bonus_rule?.model === 'B' && ` · ${k.bonus_rule.thresholds?.length || 0} порогов`}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={cn('text-lg font-semibold tabular-nums',
                          tone === 'emerald' && 'text-emerald-700',
                          tone === 'amber' && 'text-amber-700',
                          tone === 'rose' && 'text-rose-700')}>
                          {k.completionPct.toFixed(0)}%
                        </div>
                        <div className="text-[10px] text-fg-muted">
                          {Math.round(k.factScaled).toLocaleString('ru-RU')} / {k.target_value.toLocaleString('ru-RU')}
                        </div>
                      </div>
                      <button onClick={() => {
                        if (confirm(`Удалить KPI «${k.manager_name}»?`)) remove.mutate(k.id)
                      }} className="p-1.5 hover:bg-rose-100 rounded">
                        <Trash2 className="w-3.5 h-3.5 text-rose-600" />
                      </button>
                    </div>
                  )
                })}
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}


function KPICard({ label, value, subtitle, tone }: {
  label: string; value: string; subtitle?: string;
  tone?: 'emerald' | 'amber' | 'rose'
}) {
  return (
    <Card className="p-3">
      <div className="text-xs text-fg-muted">{label}</div>
      <div className={cn('text-xl font-semibold tabular-nums',
        tone === 'emerald' && 'text-emerald-700',
        tone === 'amber' && 'text-amber-700',
        tone === 'rose' && 'text-rose-700',
      )}>{value}</div>
      {subtitle && <div className="text-[10px] text-fg-muted mt-0.5">{subtitle}</div>}
    </Card>
  )
}
