import { useState, useMemo, useCallback } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  Lock, LockOpen, Download, RotateCcw, ChevronRight,
  Loader2, Target, CheckCircle2,
} from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Sparkline } from '@/components/ui/Sparkline'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import type { OzonAccountSummary } from '@/stores/cabinet'

// ── Types ─────────────────────────────────────────────────────────────

type Metric = 'orders' | 'revenue' | 'marginal_profit'
type Tab = 'plan' | 'fact'
type Step = 1 | 2 | 3

const METRIC_LABELS: Record<Metric, string> = {
  orders: 'Заказы (шт)',
  revenue: 'Выручка',
  marginal_profit: 'Маржинальная прибыль',
}

function isMoney(m: string) {
  return m === 'revenue' || m === 'marginal_profit'
}

function fmtVal(v: number, m: string) {
  return isMoney(m) ? formatCurrency(v) : formatNumber(v)
}

interface ForecastSku {
  sku_id: string
  offer_id: string
  name: string
  cabinet_id: string
  fact: number
  forecast: number
  season_weights: number[]
  reliability: 'low' | 'medium' | 'high'
}

interface ChartPoint {
  date: string
  value: number
}

interface ForecastResp {
  items: ForecastSku[]
  history: ChartPoint[]
  forecast_series: ChartPoint[]
}

interface PlanListItem {
  id: string
  period_from: string
  period_to: string
  metric: string
}

interface FactRow {
  metric: string
  label: string
  fact: number
  plan: number | null
  pct: number | null
}

interface FactResp {
  plan_id: string | null
  period_from: string
  period_to: string
  rows: FactRow[]
}

// ── Date helpers ──────────────────────────────────────────────────────

function isoDate(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function isoToday() { return isoDate(new Date()) }

function isoDaysAgo(n: number) {
  const d = new Date(); d.setDate(d.getDate() - n); return isoDate(d)
}

function isoNextMonthStart() {
  const d = new Date(); return isoDate(new Date(d.getFullYear(), d.getMonth() + 1, 1))
}

function isoNextMonthEnd() {
  const d = new Date(); return isoDate(new Date(d.getFullYear(), d.getMonth() + 2, 0))
}

function weekLabels(from: string, count: number): string[] {
  const d = new Date(from)
  return Array.from({ length: count }, (_, i) => {
    const w = new Date(d); w.setDate(w.getDate() + i * 7)
    return `${String(w.getDate()).padStart(2, '0')}.${String(w.getMonth() + 1).padStart(2, '0')}`
  })
}

// ── Reliability badge ─────────────────────────────────────────────────

const RELIABILITY: Record<string, { label: string; cls: string }> = {
  low:    { label: 'Низкая надёжность',   cls: 'bg-rose-50 text-rose-700 border-rose-200' },
  medium: { label: 'Средняя надёжность',  cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  high:   { label: 'Высокая надёжность',  cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
}

// ── Step indicator ────────────────────────────────────────────────────

function StepIndicator({ step }: { step: Step }) {
  const steps: [Step, string][] = [[1, 'Параметры'], [2, 'Планы по товарам'], [3, 'По дням']]
  return (
    <div className="flex items-center">
      {steps.map(([n, label], i) => {
        const done = step > n
        const active = step === n
        return (
          <div key={n} className="flex items-center">
            <div className={cn(
              'flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium',
              active ? 'bg-fg text-bg' : done ? 'text-emerald-700' : 'text-fg-muted',
            )}>
              <span className={cn(
                'w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold border',
                active ? 'border-bg bg-bg text-fg' :
                done   ? 'bg-emerald-500 border-emerald-500 text-white' :
                         'border-border-subtle text-fg-muted',
              )}>
                {done ? '✓' : n}
              </span>
              {label}
            </div>
            {i < steps.length - 1 && (
              <div className={cn('w-8 h-px', done ? 'bg-emerald-400' : 'bg-border-subtle')} />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Cabinet multiselect ───────────────────────────────────────────────

function CabinetSelect({
  cabinets, selected, onChange,
}: {
  cabinets: OzonAccountSummary[]
  selected: string[]
  onChange: (ids: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const label =
    selected.length === 0 ? 'Все кабинеты' :
    selected.length === 1 ? (cabinets.find((c) => c.id === selected[0])?.name ?? '1 кабинет') :
    `${selected.length} кабинета`

  const toggle = (id: string) =>
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id])

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="h-9 px-3 rounded-md border border-border bg-surface text-sm w-full text-left flex items-center justify-between gap-2 min-w-[180px]"
      >
        <span className="truncate">{label}</span>
        <ChevronRight className={cn('w-3.5 h-3.5 text-fg-muted flex-shrink-0 transition-transform', open && 'rotate-90')} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute top-full mt-1 left-0 z-50 bg-surface border border-border rounded-md shadow-elev w-full min-w-[220px] py-1 max-h-60 overflow-y-auto">
            <button
              className={cn(
                'w-full px-3 py-1.5 text-sm text-left hover:bg-bg-subtle',
                selected.length === 0 && 'font-medium text-fg',
              )}
              onClick={() => { onChange([]); setOpen(false) }}
            >
              Все кабинеты
            </button>
            {cabinets.map((c) => (
              <label key={c.id} className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-bg-subtle cursor-pointer">
                <input
                  type="checkbox"
                  checked={selected.includes(c.id)}
                  onChange={() => toggle(c.id)}
                  className="accent-fg"
                />
                <span className="truncate">{c.name}</span>
              </label>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────

export function PlanVsFact() {
  const [tab, setTab] = useState<Tab>('plan')
  const [step, setStep] = useState<Step>(1)

  // Step 1
  const [selectedCabinets, setSelectedCabinets] = useState<string[]>([])
  const [metric, setMetric] = useState<Metric>('orders')
  const [analysisFrom, setAnalysisFrom] = useState(isoDaysAgo(90))
  const [analysisTo, setAnalysisTo] = useState(isoToday())
  const [forecastFrom, setForecastFrom] = useState(isoNextMonthStart())
  const [forecastTo, setForecastTo] = useState(isoNextMonthEnd())

  // Step 2
  const [forecast, setForecast] = useState<ForecastResp | null>(null)
  const [planItems, setPlanItems] = useState<Record<string, { plan: string; locked: boolean }>>({})
  const [globalPlan, setGlobalPlan] = useState('')

  // Saved plan
  const [savedPlanId, setSavedPlanId] = useState<string | null>(null)

  // Cabinets
  const { data: cabinets = [] } = useQuery<OzonAccountSummary[]>({
    queryKey: ['ozon-accounts'],
    queryFn: async () => (await api.get('/ozon-accounts/')).data,
    staleTime: 60_000,
  })

  // Plan list (for Fact tab)
  const { data: planList = [] } = useQuery<PlanListItem[]>({
    queryKey: ['plan-sales-list'],
    queryFn: async () => (await api.get('/plan/sales')).data,
    enabled: tab === 'fact',
  })

  const activePlanId = savedPlanId ?? planList[0]?.id ?? null

  // Fact data — с планом (если план есть)
  const { data: planFact, isLoading: planFactLoading } = useQuery<FactResp>({
    queryKey: ['plan-fact', activePlanId],
    queryFn: async () => (await api.get(`/plan/sales/${activePlanId}/fact`)).data,
    enabled: tab === 'fact' && !!activePlanId,
  })

  // Fact data — без плана: MTD текущего месяца
  const { data: currentFact, isLoading: currentFactLoading } = useQuery<FactResp>({
    queryKey: ['current-fact'],
    queryFn: async () => (await api.get('/plan/sales/current-fact')).data,
    enabled: tab === 'fact' && !activePlanId,
  })

  const fact = planFact ?? currentFact
  const factLoading = planFactLoading || currentFactLoading

  // Forecast
  const forecastMut = useMutation({
    mutationFn: async () =>
      (await api.post('/plan/forecast', {
        cabinet_ids: selectedCabinets,
        metric,
        analysis_from: analysisFrom,
        analysis_to: analysisTo,
        forecast_from: forecastFrom,
        forecast_to: forecastTo,
      })).data as ForecastResp,
    onSuccess: (data) => {
      setForecast(data)
      const items: Record<string, { plan: string; locked: boolean }> = {}
      let total = 0
      ;(Array.isArray(data?.items) ? data.items : []).forEach((it) => {
        const v = Math.round(it.forecast)
        items[it.sku_id] = { plan: String(v), locked: false }
        total += v
      })
      setPlanItems(items)
      setGlobalPlan(String(total))
      setStep(2)
    },
  })

  // Save plan
  const saveMut = useMutation({
    mutationFn: async () => {
      const { data: plan } = await api.post('/plan/sales', {
        cabinet_ids: selectedCabinets,
        metric,
        period_from: forecastFrom,
        period_to: forecastTo,
      })
      const items = (Array.isArray(forecast?.items) ? forecast!.items : []).map((it) => ({
        sku_id: it.sku_id,
        plan_value: parseFloat(planItems[it.sku_id]?.plan || '0'),
        locked: planItems[it.sku_id]?.locked ?? false,
      }))
      await api.post(`/plan/sales/${plan.id}/items`, { items })
      await api.post(`/plan/sales/${plan.id}/distribute`)
      return plan as { id: string }
    },
    onSuccess: ({ id }) => setSavedPlanId(id),
  })

  // Global plan redistribution
  const handleGlobalPlan = useCallback((val: string) => {
    setGlobalPlan(val)
    if (!forecast) return
    const total = parseFloat(val)
    if (isNaN(total)) return
    const forecastItems = Array.isArray(forecast.items) ? forecast.items : []
    const unlocked = forecastItems.filter((it) => !planItems[it.sku_id]?.locked)
    const lockedSum = forecastItems
      .filter((it) => planItems[it.sku_id]?.locked)
      .reduce((s, it) => s + parseFloat(planItems[it.sku_id]?.plan || '0'), 0)
    const remaining = total - lockedSum
    const fcstSum = unlocked.reduce((s, it) => s + it.forecast, 0) || 1
    setPlanItems((prev) => {
      const next = { ...prev }
      unlocked.forEach((it) => {
        next[it.sku_id] = { ...next[it.sku_id], plan: String(Math.round((it.forecast / fcstSum) * remaining)) }
      })
      return next
    })
  }, [forecast, planItems])

  const handleReset = () => {
    if (!forecast) return
    const items: Record<string, { plan: string; locked: boolean }> = {}
    let total = 0
    ;(Array.isArray(forecast.items) ? forecast.items : []).forEach((it) => {
      const v = Math.round(it.forecast)
      items[it.sku_id] = { plan: String(v), locked: false }
      total += v
    })
    setPlanItems(items)
    setGlobalPlan(String(total))
  }

  const toggleLock = (skuId: string) =>
    setPlanItems((prev) => ({
      ...prev,
      [skuId]: { ...prev[skuId], locked: !prev[skuId]?.locked },
    }))

  // Totals
  const totals = useMemo(() => {
    if (!forecast) return { fact: 0, forecast: 0, plan: 0 }
    return (Array.isArray(forecast.items) ? forecast.items : []).reduce((acc, it) => ({
      fact:     acc.fact     + it.fact,
      forecast: acc.forecast + it.forecast,
      plan:     acc.plan     + parseFloat(planItems[it.sku_id]?.plan || '0'),
    }), { fact: 0, forecast: 0, plan: 0 })
  }, [forecast, planItems])

  // Reliability (most common)
  const reliabilityKey = useMemo(() => {
    if (!Array.isArray(forecast?.items) || !forecast.items.length) return 'medium'
    const cnt: Record<string, number> = {}
    forecast.items.forEach((it) => { cnt[it.reliability] = (cnt[it.reliability] || 0) + 1 })
    return Object.entries(cnt).sort((a, b) => b[1] - a[1])[0][0]
  }, [forecast])

  // Chart data
  const chartData = useMemo(() => {
    if (!forecast) return []
    const history = (Array.isArray(forecast.history) ? forecast.history : []).filter(Boolean)
    const forecastSeries = (Array.isArray(forecast.forecast_series) ? forecast.forecast_series : []).filter(Boolean)
    const forecastItems = (Array.isArray(forecast.items) ? forecast.items : []).filter(Boolean)
    const histMap = new Map(history.map((p) => [p?.date ?? '', p?.value ?? 0]))
    const fcstMap = new Map(forecastSeries.map((p) => [p?.date ?? '', p?.value ?? 0]))
    const dates = [...new Set([...histMap.keys(), ...fcstMap.keys()])].filter(Boolean).sort()
    const fcstTotal = forecastSeries.reduce((s, p) => s + (p?.value ?? 0), 0) || 1
    const planTotal = forecastItems.reduce((s, it) => s + parseFloat(planItems[it?.sku_id]?.plan || '0'), 0)
    const ratio = planTotal / fcstTotal
    return dates.map((date) => ({
      date: date.slice(5),
      history:  histMap.get(date) ?? null,
      forecast: fcstMap.get(date) ?? null,
      plan:     fcstMap.has(date) ? Math.round(fcstMap.get(date)! * ratio) : null,
    }))
  }, [forecast, planItems])

  // Weekly distribution for Step 3
  const weekCount = (Array.isArray(forecast?.items?.[0]?.season_weights) ? forecast!.items[0].season_weights.length : null) ?? 4
  const wLabels = useMemo(() => weekLabels(forecastFrom, weekCount), [forecastFrom, weekCount])

  const weeklyRows = useMemo(() => {
    if (!forecast) return []
    return (Array.isArray(forecast.items) ? forecast.items : []).map((it) => {
      const total = parseFloat(planItems[it.sku_id]?.plan || '0')
      const weights = Array.isArray(it.season_weights) ? it.season_weights : []
      const sumW = weights.reduce((s, w) => s + w, 0) || 1
      const weeks = weights.map((w) => Math.round((w / sumW) * total))
      return { sku_id: it.sku_id, offer_id: it.offer_id, name: it.name, weeks }
    })
  }, [forecast, planItems])

  // ── Render ────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">План / Факт</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          Поставьте план на период — система покажет прогноз и отследит исполнение
        </p>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-2">
        {(['plan', 'fact'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              'px-4 py-1.5 rounded-md text-sm border transition-colors',
              tab === t
                ? 'border-fg bg-fg text-bg'
                : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
            )}
          >
            {t === 'plan' ? 'Постановка плана' : 'Факт'}
          </button>
        ))}
      </div>

      {/* ═══ PLAN TAB ═══ */}
      {tab === 'plan' && (
        <div className="flex flex-col gap-4">
          <StepIndicator step={step} />

          {/* ─── Step 1: Parameters ─── */}
          {step === 1 && (
            <Card className="p-5 flex flex-col gap-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                <div className="sm:col-span-2 md:col-span-1">
                  <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Кабинет</label>
                  <CabinetSelect
                    cabinets={cabinets}
                    selected={selectedCabinets}
                    onChange={setSelectedCabinets}
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Метрика</label>
                  <select
                    value={metric}
                    onChange={(e) => setMetric(e.target.value as Metric)}
                    className="h-9 px-3 rounded-md border border-border bg-surface text-sm w-full"
                  >
                    {(Object.entries(METRIC_LABELS) as [Metric, string][]).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <p className="text-[11px] font-medium text-fg-muted uppercase mb-2">Период анализа</p>
                <div className="flex flex-wrap gap-3">
                  <div>
                    <label className="block text-[11px] text-fg-muted mb-1">От</label>
                    <Input type="date" value={analysisFrom} onChange={(e) => setAnalysisFrom(e.target.value)} className="w-[150px]" />
                  </div>
                  <div>
                    <label className="block text-[11px] text-fg-muted mb-1">До</label>
                    <Input type="date" value={analysisTo} onChange={(e) => setAnalysisTo(e.target.value)} className="w-[150px]" />
                  </div>
                </div>
              </div>

              <div>
                <p className="text-[11px] font-medium text-fg-muted uppercase mb-2">Период прогноза</p>
                <div className="flex flex-wrap gap-3">
                  <div>
                    <label className="block text-[11px] text-fg-muted mb-1">От</label>
                    <Input type="date" value={forecastFrom} onChange={(e) => setForecastFrom(e.target.value)} className="w-[150px]" />
                  </div>
                  <div>
                    <label className="block text-[11px] text-fg-muted mb-1">До</label>
                    <Input type="date" value={forecastTo} onChange={(e) => setForecastTo(e.target.value)} className="w-[150px]" />
                  </div>
                </div>
              </div>

              {forecastMut.isError && (
                <p className="text-sm text-rose-700">Ошибка прогноза. Проверьте параметры и попробуйте снова.</p>
              )}

              {forecastMut.isPending && (
                <div className="grid grid-cols-3 gap-2">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className="h-7 rounded-md bg-bg-subtle animate-pulse" />
                  ))}
                </div>
              )}

              <div className="flex justify-end">
                <Button onClick={() => forecastMut.mutate()} disabled={forecastMut.isPending}>
                  {forecastMut.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                  {forecastMut.isPending ? 'Считаем…' : 'Спрогнозировать'}
                </Button>
              </div>
            </Card>
          )}

          {/* ─── Step 2: SKU table + chart ─── */}
          {step === 2 && forecast && (
            <div className="flex flex-col gap-4">
              {/* Controls row */}
              <Card className="p-4 flex flex-wrap items-end gap-3">
                <div>
                  <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Общий план</label>
                  <Input
                    type="number"
                    value={globalPlan}
                    onChange={(e) => handleGlobalPlan(e.target.value)}
                    className="w-[160px]"
                  />
                </div>
                <span className={cn(
                  'px-2.5 py-1 rounded-full text-xs font-medium border self-end',
                  RELIABILITY[reliabilityKey]?.cls,
                )}>
                  {RELIABILITY[reliabilityKey]?.label}
                </span>
                <div className="ml-auto flex flex-wrap gap-2">
                  <Button variant="ghost" size="sm" onClick={() => {}}>
                    <Download className="w-4 h-4" /> Excel
                  </Button>
                  <Button variant="secondary" size="sm" onClick={handleReset}>
                    <RotateCcw className="w-4 h-4" /> Сбросить
                  </Button>
                  <Button size="sm" onClick={() => setStep(3)}>
                    Распределить по дням <ChevronRight className="w-4 h-4" />
                  </Button>
                </div>
              </Card>

              {/* Table + Chart */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                {/* SKU table */}
                <div className="lg:col-span-2">
                  <Card className="overflow-hidden">
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                          <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                            <th className="py-2.5 px-3 font-medium">Артикул</th>
                            <th className="py-2.5 px-3 font-medium">Название</th>
                            <th className="py-2.5 px-3 font-medium text-right">Факт</th>
                            <th className="py-2.5 px-3 font-medium text-right">Прогноз</th>
                            <th className="py-2.5 px-3 font-medium text-right">План</th>
                            <th className="py-2.5 px-3 font-medium w-10" />
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border-subtle">
                          {(Array.isArray(forecast.items) ? forecast.items : []).map((it) => {
                            const item = planItems[it.sku_id] ?? { plan: String(Math.round(it.forecast)), locked: false }
                            return (
                              <tr key={it.sku_id} className="hover:bg-bg-subtle/40">
                                <td className="py-2 px-3 font-mono text-xs text-fg-muted whitespace-nowrap">{it.offer_id}</td>
                                <td className="py-2 px-3 max-w-[180px]">
                                  <span className="line-clamp-1 text-sm text-fg">{it.name}</span>
                                </td>
                                <td className="py-2 px-3 text-right tabular-nums text-fg-muted whitespace-nowrap">
                                  {fmtVal(it.fact, metric)}
                                </td>
                                <td className="py-2 px-3 text-right tabular-nums text-blue-600 whitespace-nowrap">
                                  {fmtVal(it.forecast, metric)}
                                </td>
                                <td className="py-2 px-3">
                                  <Input
                                    type="number"
                                    value={item.plan}
                                    disabled={item.locked}
                                    onChange={(e) =>
                                      setPlanItems((prev) => ({
                                        ...prev,
                                        [it.sku_id]: { ...prev[it.sku_id], plan: e.target.value },
                                      }))
                                    }
                                    className="w-24 text-right tabular-nums"
                                  />
                                </td>
                                <td className="py-2 px-3 text-center">
                                  <button
                                    onClick={() => toggleLock(it.sku_id)}
                                    className="p-1 rounded hover:bg-bg-subtle"
                                    title={item.locked ? 'Разблокировать' : 'Заблокировать'}
                                  >
                                    {item.locked
                                      ? <Lock className="w-4 h-4 text-amber-600" />
                                      : <LockOpen className="w-4 h-4 text-fg-subtle" />}
                                  </button>
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                        <tfoot className="border-t-2 border-border text-xs font-semibold bg-bg-subtle/50">
                          <tr>
                            <td className="py-2.5 px-3 text-fg-muted" colSpan={2}>Итого</td>
                            <td className="py-2.5 px-3 text-right tabular-nums text-fg-muted">
                              {fmtVal(totals.fact, metric)}
                            </td>
                            <td className="py-2.5 px-3 text-right tabular-nums text-blue-600">
                              {fmtVal(totals.forecast, metric)}
                            </td>
                            <td className="py-2.5 px-3 text-right tabular-nums text-emerald-700">
                              {fmtVal(totals.plan, metric)}
                            </td>
                            <td />
                          </tr>
                        </tfoot>
                      </table>
                    </div>
                  </Card>
                </div>

                {/* Chart */}
                <Card className="p-4 flex flex-col gap-2">
                  <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">Динамика</p>
                  <ResponsiveContainer width="100%" height={260}>
                    <LineChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle, #e5e7eb)" />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 10, fill: 'var(--fg-muted, #6b7280)' }}
                        tickLine={false}
                        interval="preserveStartEnd"
                      />
                      <YAxis
                        tick={{ fontSize: 10, fill: 'var(--fg-muted, #6b7280)' }}
                        tickLine={false}
                        tickFormatter={(v: number) => isMoney(metric) ? `${Math.round(v / 1000)}к` : String(v)}
                      />
                      <Tooltip
                        contentStyle={{
                          background: 'var(--surface, #fff)',
                          border: '1px solid var(--border, #e5e7eb)',
                          borderRadius: 6,
                          fontSize: 12,
                        }}
                        formatter={(v: number) => fmtVal(v, metric)}
                      />
                      <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
                      <Line
                        dataKey="history"
                        name="История"
                        stroke="#94a3b8"
                        strokeWidth={2}
                        dot={false}
                        connectNulls={false}
                      />
                      <Line
                        dataKey="forecast"
                        name="Прогноз"
                        stroke="#3b82f6"
                        strokeWidth={2}
                        strokeDasharray="5 3"
                        dot={false}
                        connectNulls={false}
                      />
                      <Line
                        dataKey="plan"
                        name="План"
                        stroke="#10b981"
                        strokeWidth={2}
                        dot={false}
                        connectNulls={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </Card>
              </div>
            </div>
          )}

          {/* ─── Step 3: Weekly distribution ─── */}
          {step === 3 && forecast && (
            <div className="flex flex-col gap-4">
              <Card className="overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                      <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                        <th className="py-2.5 px-3 font-medium sticky left-0 bg-bg-subtle/80 min-w-[180px]">Товар</th>
                        {wLabels.map((w, i) => (
                          <th key={i} className="py-2.5 px-3 font-medium text-right whitespace-nowrap">{w}</th>
                        ))}
                        <th className="py-2.5 px-3 font-medium text-right w-28">График</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-subtle">
                      {weeklyRows.map((row) => (
                        <tr key={row.sku_id} className="hover:bg-bg-subtle/40">
                          <td className="py-2.5 px-3 sticky left-0 bg-bg border-r border-border-subtle/50">
                            <div className="text-[11px] font-mono text-fg-muted">{row.offer_id}</div>
                            <div className="text-sm text-fg line-clamp-1 max-w-[160px]">{row.name}</div>
                          </td>
                          {row.weeks.map((v, i) => (
                            <td key={i} className="py-2.5 px-3 text-right tabular-nums text-fg-muted whitespace-nowrap">
                              {fmtVal(v, metric)}
                            </td>
                          ))}
                          <td className="py-2.5 px-3 w-28 text-emerald-600">
                            <Sparkline points={row.weeks} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>

              <div className="flex items-center justify-between gap-3">
                <Button variant="ghost" onClick={() => setStep(2)}>
                  ← Назад
                </Button>
                <Button
                  onClick={() => saveMut.mutate()}
                  disabled={saveMut.isPending || saveMut.isSuccess}
                >
                  {saveMut.isPending ? (
                    <><Loader2 className="w-4 h-4 animate-spin" /> Сохраняем…</>
                  ) : saveMut.isSuccess ? (
                    <><CheckCircle2 className="w-4 h-4" /> Сохранено</>
                  ) : (
                    'Сохранить планы'
                  )}
                </Button>
              </div>

              {saveMut.isSuccess && (
                <Card className="p-4 flex items-center gap-3 bg-emerald-50 border-emerald-200">
                  <CheckCircle2 className="w-5 h-5 text-emerald-700 shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-emerald-900">План сохранён</p>
                    <p className="text-xs text-emerald-700">
                      Перейдите на вкладку «Факт» для отслеживания исполнения
                    </p>
                  </div>
                  <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setTab('fact')}>
                    К факту →
                  </Button>
                </Card>
              )}

              {saveMut.isError && (
                <p className="text-sm text-rose-700">Ошибка сохранения. Попробуйте ещё раз.</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* ═══ FACT TAB ═══ */}
      {tab === 'fact' && (
        <>
          {factLoading ? (
            <Card className="py-14 flex justify-center">
              <Loader2 className="w-5 h-5 animate-spin text-fg-muted" />
            </Card>
          ) : fact ? (
            <Card className="overflow-hidden">
              <div className="px-5 py-3 border-b border-border-subtle bg-bg-subtle/50 flex items-center justify-between">
                <p className="text-xs text-fg-muted">
                  Период: {fact.period_from} … {fact.period_to}
                </p>
                {!fact.plan_id && (
                  <span className="text-xs text-fg-muted italic">план не задан</span>
                )}
              </div>
              <table className="w-full text-sm">
                <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                  <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                    <th className="py-2.5 px-4 font-medium">Метрика</th>
                    <th className="py-2.5 px-4 font-medium text-right">Факт</th>
                    <th className="py-2.5 px-4 font-medium text-right">План</th>
                    <th className="py-2.5 px-4 font-medium text-right">%</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {(Array.isArray(fact.rows) ? fact.rows : []).map((r) => (
                    <tr key={r.metric} className="hover:bg-bg-subtle/40">
                      <td className="py-3 px-4 font-medium text-fg">{r.label}</td>
                      <td className="py-3 px-4 text-right tabular-nums text-fg">
                        {fmtVal(r.fact, r.metric)}
                      </td>
                      <td className="py-3 px-4 text-right tabular-nums text-fg-muted">
                        {r.plan != null ? fmtVal(r.plan, r.metric) : '—'}
                      </td>
                      <td className="py-3 px-4 text-right">
                        {r.pct != null ? (
                          <span className={cn(
                            'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
                            r.pct >= 100 ? 'bg-emerald-50 text-emerald-700' :
                            r.pct >= 80  ? 'bg-amber-50 text-amber-700' :
                                           'bg-rose-50 text-rose-700',
                          )}>
                            {r.pct >= 100 ? '🟢' : r.pct >= 80 ? '🟡' : '🔴'} {r.pct}%
                          </span>
                        ) : (
                          <span className="text-fg-muted text-xs">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          ) : (
            <Card className="py-14 flex flex-col items-center gap-3 text-fg-muted">
              <Target className="w-8 h-8 text-fg-subtle" />
              <p className="text-sm">Нет данных за текущий месяц</p>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
