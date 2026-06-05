/**
 * /analytics/plan-fact — План продаж v2 (bottom-up + игровой режим).
 *
 * Tabs: Постановка плана | Факт | KPI | Игровой режим
 * Wizard 3 шага (bottom-up):
 *   1) Кабинеты + товары + метрика + период → загрузка SKU
 *   2) Per-SKU plan (стартовое = прогноз), правка, авто-сумма ↑
 *   3) SKU × недели + сохранение
 */
import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  LineChart, Line, BarChart, Bar, Cell, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts'
import {
  Target, TrendingUp, AlertTriangle, Save, Lock, Unlock, Trash2,
  FileSpreadsheet, Sliders, BarChart3, Award, ArrowRight, RotateCcw,
  Loader2, Gauge, Zap, Trophy, Search,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { AskAIButton } from '@/components/AskAIButton'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

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
interface BottomupItem {
  product_id: string | null; sku: string | null; name: string | null
  offer_id: string | null
  cabinet_id: string | null; cabinet_name: string | null
  analysis_value: number; forecast_value: number
  plan_value: number; share_pct: number
}
interface BottomupResp {
  items: BottomupItem[]
  total_analysis: number; total_forecast: number
  by_cabinet: Array<{
    cabinet_id: string | null; cabinet_name: string
    analysis_sum: number; forecast_sum: number; plan_sum: number
    skus_count: number
  }>
}
interface PlanRow {
  id: string; name: string; scope_type: string; scope_ref: string | null
  metric_code: string; period_start: string; period_end: string
  analysis_start: string; analysis_end: string
  target_value: number; base_forecast: number | null
  distribution_mode: string; source_pref: string
  note: string | null; created_at: string; items_count: number
}
interface Cabinet { id: string; name: string }

const METRIC_OPTIONS = [
  { code: 'orders', label: 'Заказы (шт)' },
  { code: 'units', label: 'Единицы (выкуплено)' },
  { code: 'revenue', label: 'Выручка (₽)' },
  { code: 'gross_profit', label: 'Маржинальная прибыль (₽)' },
]

function isoDate(d: Date) { return d.toISOString().slice(0, 10) }

function exportItemsCsv(items: BottomupItem[]) {
  const header = 'cabinet;offer_id;name;analysis_value;forecast_value;plan_value\n'
  const rows = items.map((i) => [
    i.cabinet_name || '',
    i.offer_id || '',
    (i.name || '').replace(/;/g, ','),
    i.analysis_value.toFixed(2),
    i.forecast_value.toFixed(2),
    i.plan_value.toFixed(2),
  ].join(';')).join('\n')
  const blob = new Blob(['﻿' + header + rows], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'plan_skus.csv'; a.click()
  URL.revokeObjectURL(url)
}

export function SalesPlan() {
  const [tab, setTab] = useState<'wizard' | 'fact' | 'kpi' | 'game'>('wizard')

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
            <Target className="w-6 h-6 text-purple-500" />
            План продаж
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            Bottom-up: прогноз per-SKU → правка → сумма ↑. Факт = брутто − возвраты.
          </p>
        </div>
        <AskAIButton
          context={{ type: 'screen', source_page: 'sales-plan', source_label: 'План продаж',
            metrics: ['target', 'fact', 'completion_pct', 'run_rate'] }}
          question="Какой план реалистичен на месяц? Где риски невыполнения?"
        />
      </div>

      <div className="flex gap-1 border-b border-border-subtle flex-wrap">
        {[
          { key: 'wizard', label: 'Постановка плана', icon: Sliders },
          { key: 'fact', label: 'Факт', icon: BarChart3 },
          { key: 'kpi', label: 'KPI менеджмента', icon: Award },
          { key: 'game', label: 'Игровой режим', icon: Gauge },
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
      {tab === 'game' && <GameTab />}
    </div>
  )
}


// ===========================================
// WIZARD — bottom-up
// ===========================================

function WizardTab() {
  const qc = useQueryClient()
  const [step, setStep] = useState<1 | 2 | 3>(1)

  const today = new Date()
  const monthAgo = new Date(today.getTime() - 90 * 86400 * 1000)
  const nextMonthEnd = new Date(today.getFullYear(), today.getMonth() + 1, 0)
  const nextMonthStart = new Date(today.getFullYear(), today.getMonth() + 1, 1)

  const [metric, setMetric] = useState('orders')
  const [analysisFrom, setAnalysisFrom] = useState(isoDate(monthAgo))
  const [analysisTo, setAnalysisTo] = useState(isoDate(today))
  const [forecastFrom, setForecastFrom] = useState(isoDate(nextMonthStart))
  const [forecastTo, setForecastTo] = useState(isoDate(nextMonthEnd))
  const [selectedCabinets, setSelectedCabinets] = useState<string[]>([])
  const [productSearch, setProductSearch] = useState('')
  const [planName, setPlanName] = useState('')
  const [forecast, setForecast] = useState<ForecastResp | null>(null)
  const [items, setItems] = useState<BottomupItem[]>([])
  const [locked, setLocked] = useState<Set<string>>(new Set())
  const [overallPlan, setOverallPlan] = useState(0)
  const [savedPlanId, setSavedPlanId] = useState<string | null>(null)

  const { data: cabinets = [] } = useQuery<Cabinet[]>({
    queryKey: ['cabinets'],
    queryFn: async () => (await api.get('/ozon-accounts/')).data || [],
  })

  const calcForecast = useMutation<ForecastResp, any, void>({
    mutationFn: async () => (await api.post('/plans/forecast', {
      metric,
      analysis_start: analysisFrom, analysis_end: analysisTo,
      forecast_start: forecastFrom, forecast_end: forecastTo,
    })).data,
    onSuccess: (data) => setForecast(data),
  })

  const loadBottomup = useMutation<BottomupResp, any, void>({
    mutationFn: async () => (await api.post('/plans/bottomup', {
      metric,
      analysis_start: analysisFrom, analysis_end: analysisTo,
      forecast_start: forecastFrom, forecast_end: forecastTo,
      cabinet_ids: selectedCabinets,
    })).data,
    onSuccess: (data) => {
      setItems(data.items)
      setOverallPlan(data.total_forecast)
    },
  })

  // Авто-сумма plan_value
  const totalPlan = useMemo(
    () => items.reduce((s, i) => s + (Number(i.plan_value) || 0), 0),
    [items]
  )
  const byCabinetTotals = useMemo(() => {
    const m: Record<string, { name: string; sum: number; n: number }> = {}
    items.forEach((i) => {
      const cid = i.cabinet_id || '—'
      if (!m[cid]) m[cid] = { name: i.cabinet_name || '—', sum: 0, n: 0 }
      m[cid].sum += Number(i.plan_value) || 0
      m[cid].n += 1
    })
    return Object.values(m)
  }, [items])

  // Top-down: правка общего значения → распределить дельту по unlocked
  function applyOverall(newOverall: number) {
    const delta = newOverall - totalPlan
    if (Math.abs(delta) < 0.01) return
    const unlocked = items.filter((i) => !locked.has(i.product_id || ''))
    if (unlocked.length === 0) return
    const unlockedSum = unlocked.reduce((s, i) => s + i.plan_value, 0)
    if (unlockedSum <= 0) return
    setItems(items.map((i) => {
      if (locked.has(i.product_id || '')) return i
      const proportion = i.plan_value / unlockedSum
      return { ...i, plan_value: Math.max(0, i.plan_value + delta * proportion) }
    }))
    setOverallPlan(newOverall)
  }

  function updateItem(idx: number, newValue: number) {
    setItems(items.map((i, j) => j === idx ? { ...i, plan_value: Math.max(0, newValue) } : i))
  }

  function toggleLock(productId: string) {
    const next = new Set(locked)
    if (next.has(productId)) next.delete(productId); else next.add(productId)
    setLocked(next)
  }

  function resetToForecast() {
    setItems(items.map((i) => ({ ...i, plan_value: i.forecast_value })))
  }

  const savePlan = useMutation<{ id: string }, any, void>({
    mutationFn: async () => (await api.post('/plans', {
      name: planName || `${metric} · ${forecastFrom} … ${forecastTo}`,
      scope_type: selectedCabinets.length === 1 ? 'cabinet' : 'company',
      scope_ref: selectedCabinets.length === 1 ? selectedCabinets[0] : null,
      metric_code: metric,
      period_start: forecastFrom, period_end: forecastTo,
      analysis_start: analysisFrom, analysis_end: analysisTo,
      target_value: totalPlan,
      base_forecast: forecast?.base_forecast,
      distribution_mode: 'manual',
      items: items.map((i) => ({
        product_id: i.product_id, sku: i.sku, name: i.name, offer_id: i.offer_id,
        analysis_value: i.analysis_value, share_pct: i.share_pct,
        plan_value: i.plan_value,
      })),
    })).data,
    onSuccess: async (data) => {
      setSavedPlanId(data.id)
      // Запустить распределение по дням
      await api.post(`/plans/${data.id}/distribute-days`)
      qc.invalidateQueries({ queryKey: ['plans'] })
    },
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-xs flex-wrap">
        {[1, 2, 3].map((s) => (
          <div key={s} className="flex items-center gap-2">
            <div className={cn('w-7 h-7 rounded-full inline-flex items-center justify-center font-semibold',
              s === step ? 'bg-purple-600 text-white' :
              s < step ? 'bg-emerald-500 text-white' : 'bg-bg-subtle text-fg-muted')}>{s}</div>
            <span className={cn('font-medium', s === step ? 'text-fg' : 'text-fg-muted')}>
              {s === 1 && 'Выбор и прогноз'}
              {s === 2 && 'Планы по SKU (bottom-up)'}
              {s === 3 && 'Сетка SKU × недели'}
            </span>
            {s < 3 && <ArrowRight className="w-3.5 h-3.5 text-fg-subtle" />}
          </div>
        ))}
      </div>

      {/* === STEP 1 === */}
      {step === 1 && (
        <Card className="p-5 space-y-4">
          <h3 className="text-sm font-semibold">Шаг 1. Выбор кабинетов + товаров + прогноз</h3>

          {/* Cabinets multi-select */}
          <div>
            <label className="text-xs text-fg-muted">Кабинеты Ozon</label>
            <div className="flex flex-wrap gap-2 mt-1">
              <button onClick={() => setSelectedCabinets([])}
                      className={cn('px-3 py-1 rounded-md text-xs border',
                        selectedCabinets.length === 0
                          ? 'bg-purple-600 text-white border-purple-600'
                          : 'bg-bg border-border-subtle text-fg-muted')}>
                Все кабинеты
              </button>
              {cabinets.map((c) => (
                <button key={c.id} onClick={() => {
                  const next = selectedCabinets.includes(c.id)
                    ? selectedCabinets.filter((x) => x !== c.id)
                    : [...selectedCabinets, c.id]
                  setSelectedCabinets(next)
                }} className={cn('px-3 py-1 rounded-md text-xs border',
                  selectedCabinets.includes(c.id)
                    ? 'bg-purple-100 border-purple-400 text-purple-800'
                    : 'bg-bg border-border-subtle text-fg-muted hover:bg-bg-subtle')}>
                  {c.name}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-fg-muted">Метрика</label>
              <select value={metric} onChange={(e) => setMetric(e.target.value)}
                      className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg">
                {METRIC_OPTIONS.map((m) => <option key={m.code} value={m.code}>{m.label}</option>)}
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
            <div className="self-end flex gap-2">
              <Button variant="secondary" onClick={() => calcForecast.mutate()}
                      disabled={calcForecast.isPending}>
                {calcForecast.isPending ? '…' : 'Общий прогноз'}
              </Button>
            </div>
          </div>

          {forecast && (
            <Card className="p-3 bg-purple-50/40">
              <div className="grid grid-cols-3 gap-3 text-sm">
                <div>
                  <div className="text-xs text-fg-muted">База прогноза</div>
                  <div className="text-lg font-semibold tabular-nums">
                    {forecast.base_forecast.toLocaleString('ru-RU')}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-fg-muted">История</div>
                  <div className="text-lg font-semibold tabular-nums">
                    {forecast.history.length}д
                  </div>
                </div>
                <div>
                  <div className="text-xs text-fg-muted">Надёжность</div>
                  <div className={cn('text-lg font-semibold tabular-nums',
                    forecast.reliability === 'high' && 'text-emerald-700',
                    forecast.reliability === 'medium' && 'text-amber-700',
                    forecast.reliability === 'low' && 'text-rose-700')}>
                    {forecast.reliability_pct}%
                  </div>
                </div>
              </div>
              <div className="text-[10px] text-fg-muted mt-1">{forecast.note}</div>
            </Card>
          )}

          {forecast && (
            <Card className="p-4">
              <h4 className="text-sm font-semibold mb-2">Динамика метрики</h4>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip formatter={(v: any) => Number(v).toLocaleString('ru-RU')} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="value" data={forecast.history}
                        stroke="#6b7280" name="История" dot={false} strokeWidth={2} />
                  <Line type="monotone" dataKey="value" data={forecast.forecast_series}
                        stroke="#a78bfa" strokeDasharray="4 4"
                        name="Прогноз" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          )}

          <Button onClick={() => { loadBottomup.mutate(); setStep(2) }}
                  disabled={loadBottomup.isPending}
                  className="w-full">
            Загрузить SKU и прогнозы по каждому →
          </Button>
        </Card>
      )}

      {/* === STEP 2 === */}
      {step === 2 && (
        <Card className="p-5 space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h3 className="text-sm font-semibold">Шаг 2. Планы по SKU (bottom-up)</h3>
            <div className="flex gap-2 flex-wrap">
              <Button variant="secondary" onClick={resetToForecast} className="text-xs">
                <RotateCcw className="w-3.5 h-3.5 mr-1" /> Сбросить к прогнозу
              </Button>
              <Button variant="secondary" onClick={() => exportItemsCsv(items)} className="text-xs">
                <FileSpreadsheet className="w-3.5 h-3.5 mr-1" /> CSV
              </Button>
            </div>
          </div>

          {loadBottomup.isPending && (
            <div className="text-center py-6"><Loader2 className="w-5 h-5 animate-spin inline" /></div>
          )}

          {/* Общий план — top-down коррекция */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Card className="p-3 bg-bg-subtle/30">
              <div className="text-xs text-fg-muted">Период анализа (факт)</div>
              <div className="text-lg font-semibold tabular-nums">
                {items.reduce((s, i) => s + i.analysis_value, 0).toLocaleString('ru-RU')}
              </div>
            </Card>
            <Card className="p-3 bg-purple-50/40">
              <div className="text-xs text-fg-muted">Прогноз ∑</div>
              <div className="text-lg font-semibold tabular-nums">
                {items.reduce((s, i) => s + i.forecast_value, 0).toLocaleString('ru-RU')}
              </div>
            </Card>
            <Card className="p-3 border-2 border-purple-300">
              <div className="text-xs text-fg-muted">План ∑ (правка распределит по unlocked)</div>
              <input type="number" value={Math.round(totalPlan)}
                     onChange={(e) => applyOverall(Number(e.target.value))}
                     className="w-full px-2 py-1 mt-1 border border-purple-300 rounded text-lg font-semibold tabular-nums bg-bg" />
            </Card>
          </div>

          {/* По кабинетам */}
          {byCabinetTotals.length > 1 && (
            <Card className="p-3">
              <h4 className="text-xs font-semibold text-fg-muted uppercase mb-2">По кабинетам</h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
                {byCabinetTotals.map((c) => (
                  <div key={c.name} className="px-2 py-1 bg-bg-subtle/30 rounded">
                    <div className="text-xs text-fg-muted">{c.name} · {c.n} SKU</div>
                    <div className="font-semibold tabular-nums">{Math.round(c.sum).toLocaleString('ru-RU')}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Таблица SKU */}
          <div className="overflow-x-auto max-h-[60vh]">
            <table className="w-full text-sm">
              <thead className="text-xs text-fg-muted bg-bg-subtle/30 sticky top-0">
                <tr>
                  <th className="py-2 px-2 w-8">🔒</th>
                  <th className="py-2 px-3 text-left">Артикул</th>
                  <th className="py-2 px-3 text-left">Товар</th>
                  <th className="py-2 px-3 text-left">Кабинет</th>
                  <th className="py-2 px-3 text-right">Анализ</th>
                  <th className="py-2 px-3 text-right">Прогноз</th>
                  <th className="py-2 px-3 text-right">План</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, idx) => {
                  const isLocked = locked.has(it.product_id || '')
                  return (
                    <tr key={it.product_id || idx} className={cn(
                      'border-t border-border-subtle/40',
                      isLocked && 'bg-amber-50/30')}>
                      <td className="py-1 px-2 text-center">
                        <button onClick={() => it.product_id && toggleLock(it.product_id)}
                                title={isLocked ? 'Залочено' : 'Разлочено'}>
                          {isLocked ? <Lock className="w-3.5 h-3.5 text-amber-600" /> :
                                      <Unlock className="w-3.5 h-3.5 text-fg-subtle" />}
                        </button>
                      </td>
                      <td className="py-1 px-3 font-mono text-xs">{it.offer_id || '—'}</td>
                      <td className="py-1 px-3 max-w-[280px] truncate" title={it.name || ''}>
                        {(it.name || '').slice(0, 50)}
                      </td>
                      <td className="py-1 px-3 text-xs text-fg-muted">{it.cabinet_name || '—'}</td>
                      <td className="py-1 px-3 text-right tabular-nums text-xs">
                        {it.analysis_value.toLocaleString('ru-RU')}
                      </td>
                      <td className="py-1 px-3 text-right tabular-nums text-xs text-purple-700">
                        {it.forecast_value.toLocaleString('ru-RU')}
                      </td>
                      <td className="py-1 px-3 text-right">
                        <input type="number" value={Math.round(it.plan_value)}
                               onChange={(e) => updateItem(idx, Number(e.target.value))}
                               disabled={isLocked}
                               className={cn(
                                 'w-24 px-1 py-0.5 text-right text-sm tabular-nums border rounded bg-bg',
                                 isLocked ? 'border-amber-300 bg-amber-50' : 'border-border-subtle')} />
                      </td>
                    </tr>
                  )
                })}
                {items.length === 0 && !loadBottomup.isPending && (
                  <tr><td colSpan={7} className="py-6 text-center text-fg-muted">
                    Вернись на Шаг 1 и нажми «Загрузить SKU».
                  </td></tr>
                )}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-purple-300 font-semibold sticky bottom-0 bg-bg">
                  <td colSpan={4} className="py-2 px-3">ИТОГО ∑:</td>
                  <td className="py-2 px-3 text-right tabular-nums">
                    {items.reduce((s, i) => s + i.analysis_value, 0).toLocaleString('ru-RU')}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-purple-700">
                    {items.reduce((s, i) => s + i.forecast_value, 0).toLocaleString('ru-RU')}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-purple-700 text-base">
                    {Math.round(totalPlan).toLocaleString('ru-RU')}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>

          <div className="flex gap-2 justify-between">
            <Button variant="secondary" onClick={() => setStep(1)}>← Назад</Button>
            <Button onClick={() => setStep(3)} disabled={items.length === 0}>
              Сетка SKU × недели →
            </Button>
          </div>
        </Card>
      )}

      {/* === STEP 3 === */}
      {step === 3 && (
        <Card className="p-5 space-y-4">
          <h3 className="text-sm font-semibold">Шаг 3. Сохранение и сетка SKU × недели</h3>

          <div>
            <label className="text-xs text-fg-muted">Название плана</label>
            <input value={planName} onChange={(e) => setPlanName(e.target.value)}
                   placeholder={`${metric} · ${forecastFrom} … ${forecastTo}`}
                   className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
          </div>

          {!savedPlanId ? (
            <div className="flex gap-2 justify-between">
              <Button variant="secondary" onClick={() => setStep(2)}>← Назад</Button>
              <Button onClick={() => savePlan.mutate()} disabled={savePlan.isPending}>
                <Save className="w-4 h-4 mr-1" />
                {savePlan.isPending ? 'Сохраняю…' : 'Сохранить план + распределить по дням'}
              </Button>
            </div>
          ) : (
            <WeeksGrid planId={savedPlanId} />
          )}
        </Card>
      )}
    </div>
  )
}


function WeeksGrid({ planId }: { planId: string }) {
  const { data } = useQuery<{
    weeks: Array<{ week_start: string; label: string }>
    rows: Array<{
      item_id: string; sku: string; name: string; plan_value: number
      weeks: Array<{ week_start: string; value: number }>
    }>
  }>({
    queryKey: ['plan-weeks', planId],
    queryFn: async () => (await api.get(`/plans/${planId}/weeks`)).data,
  })

  if (!data) return <div className="text-center py-6"><Loader2 className="w-5 h-5 animate-spin inline" /></div>

  return (
    <Card className="p-3 overflow-x-auto">
      <h4 className="text-sm font-semibold mb-2">SKU × Недели</h4>
      <table className="w-full text-xs">
        <thead className="text-fg-muted">
          <tr>
            <th className="py-1 px-2 text-left">SKU</th>
            {data.weeks.map((w) => (
              <th key={w.week_start} className="py-1 px-2 text-right">{w.label}</th>
            ))}
            <th className="py-1 px-2 text-right">Σ</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.slice(0, 50).map((r) => (
            <tr key={r.item_id} className="border-t border-border-subtle/40">
              <td className="py-1 px-2 truncate max-w-[180px]">
                {r.sku} <span className="text-fg-muted text-[10px]">{(r.name || '').slice(0, 25)}</span>
              </td>
              {r.weeks.map((w) => (
                <td key={w.week_start} className="py-1 px-2 text-right tabular-nums">
                  {Math.round(w.value)}
                </td>
              ))}
              <td className="py-1 px-2 text-right tabular-nums font-semibold">
                {Math.round(r.plan_value).toLocaleString('ru-RU')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="text-[10px] text-fg-muted mt-2">
        {data.rows.length > 50 && `Показаны первые 50 из ${data.rows.length} SKU. `}
        План сохранён ✓
      </div>
    </Card>
  )
}


// ===========================================
// FACT TAB
// ===========================================

function FactTab() {
  const { data: plans = [] } = useQuery<PlanRow[]>({
    queryKey: ['plans'],
    queryFn: async () => (await api.get('/plans')).data,
  })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { data: fact } = useQuery<any>({
    queryKey: ['plan-fact', selectedId],
    queryFn: async () => (await api.get(`/plans/${selectedId}/fact`)).data,
    enabled: !!selectedId,
  })
  const { data: timeseries } = useQuery<{ series: any[]; plan_total: number; today: string }>({
    queryKey: ['plan-timeseries', selectedId],
    queryFn: async () => (await api.get(`/plans/${selectedId}/timeseries`)).data,
    enabled: !!selectedId,
  })
  const { data: hints } = useQuery<{ hints: any[]; blocked: boolean }>({
    queryKey: ['plan-stock-hint', selectedId],
    queryFn: async () => (await api.get(`/plans/${selectedId}/stock-hint`)).data,
    enabled: !!selectedId,
  })

  if (plans.length === 0) {
    return <Card className="p-8 text-center text-fg-muted">Планов нет. Создай первый.</Card>
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
          {/* Структура «Брутто − Возвраты = Нетто» */}
          {fact.revenue_breakdown && (
            <Card className="p-4 bg-blue-50/30 border-blue-200">
              <h4 className="text-xs font-semibold text-fg uppercase mb-2 flex items-center gap-1">
                <span>📊 Сверка по структуре Ozon</span>
              </h4>
              <div className="grid grid-cols-3 gap-3 text-sm">
                <div>
                  <div className="text-xs text-fg-muted">Оплачено (брутто)</div>
                  <div className="text-lg font-semibold tabular-nums">
                    {Number(fact.revenue_breakdown.gross).toLocaleString('ru-RU')} ₽
                  </div>
                </div>
                <div>
                  <div className="text-xs text-fg-muted">
                    − Возвращено ({fact.revenue_breakdown.returns_count})
                  </div>
                  <div className="text-lg font-semibold tabular-nums text-rose-700">
                    −{Number(fact.revenue_breakdown.returns).toLocaleString('ru-RU')} ₽
                  </div>
                </div>
                <div>
                  <div className="text-xs text-fg-muted">= Выручка (нетто)</div>
                  <div className="text-lg font-bold tabular-nums text-emerald-700">
                    {Number(fact.revenue_breakdown.net).toLocaleString('ru-RU')} ₽
                  </div>
                </div>
              </div>
              <div className="text-[10px] text-fg-muted mt-2">
                {fact.revenue_breakdown.formula}
              </div>
            </Card>
          )}

          {/* KPI cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KPICard label="План" value={fact.plan_value.toLocaleString('ru-RU')} />
            <KPICard label="Факт" value={fact.fact_value.toLocaleString('ru-RU')}
                     subtitle={fact.fact_source === 'realization' ? '✓ realization' :
                               'transactions ⚠️ предварит.'}
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

          {/* Дельта realization−transactions */}
          {fact.delta_realization_tx !== null && Math.abs(fact.delta_realization_tx) > 100 && (
            <Card className="p-3 bg-amber-50/30 border-amber-200 text-sm flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
              <div>
                <b>Δ realization − transactions:</b> {fact.delta_realization_tx.toLocaleString('ru-RU')} ₽
                <div className="text-xs text-fg-muted mt-1">
                  Realization (закрытый отчёт) − transactions (оперативка). Разница не прячется.
                </div>
              </div>
            </Card>
          )}

          {/* Stock hints */}
          {hints && hints.hints.length > 0 && (
            <Card className="p-3 bg-yellow-50/40 border-yellow-200">
              <h4 className="text-xs font-semibold text-yellow-900 uppercase mb-2 flex items-center gap-1">
                🟡 Подсказки по складу ({hints.hints.length})
              </h4>
              <div className="space-y-1 text-sm max-h-40 overflow-y-auto">
                {hints.hints.slice(0, 10).map((h: any) => (
                  <div key={h.product_id} className="text-xs text-yellow-900">
                    <span className="font-mono">{h.sku}</span>: {h.message}
                  </div>
                ))}
              </div>
              <div className="text-[10px] text-fg-muted mt-1">
                Подсказка не блокирует план. Иди в /procurement докинуть поставку.
              </div>
            </Card>
          )}

          {/* Burn-up */}
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
                  <Line type="monotone" dataKey="plan_cum" stroke="#6b7280"
                        name="План pro-rata" dot={false} strokeWidth={2} />
                  <Line type="monotone" dataKey="fact_cum" stroke="#10b981"
                        name="Факт" dot={false} strokeWidth={2.5} />
                  <Line type="monotone" dataKey="run_rate_cum" stroke="#f59e0b"
                        strokeDasharray="4 4" name="Run-rate" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          )}

          {/* Bridge */}
          {fact.bridge && fact.bridge.length > 0 && (
            <Card className="p-4">
              <h4 className="text-sm font-semibold mb-3">Bridge отклонения</h4>
              <ResponsiveContainer width="100%" height={200}>
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
            </Card>
          )}
        </>
      )}
    </div>
  )
}


// ===========================================
// KPI TAB
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
    return <Card className="p-8 text-center text-fg-muted">Создай план сначала.</Card>
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
                     placeholder="ФИО"
                     className="px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
              <select value={form.metric}
                      onChange={(e) => setForm({ ...form, metric: e.target.value })}
                      className="px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg">
                {METRIC_OPTIONS.map((m) => <option key={m.code} value={m.code}>{m.label}</option>)}
              </select>
              <input type="number" value={form.target}
                     onChange={(e) => setForm({ ...form, target: e.target.value })}
                     placeholder="Цель"
                     className="px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
              <select value={form.model}
                      onChange={(e) => setForm({ ...form, model: e.target.value as any })}
                      className="px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg">
                <option value="A">A: % от чистой</option>
                <option value="B">B: пороги</option>
              </select>
            </div>
            {form.model === 'A' ? (
              <div className="mt-3 max-w-xs">
                <label className="text-xs text-fg-muted">% от чистой прибыли</label>
                <input type="number" step="0.1" value={form.pctOfNet}
                       onChange={(e) => setForm({ ...form, pctOfNet: e.target.value })}
                       className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
              </div>
            ) : (
              <div className="mt-3 grid grid-cols-2 gap-2 max-w-md">
                <input type="number" value={form.threshold1}
                       onChange={(e) => setForm({ ...form, threshold1: e.target.value })}
                       placeholder="Порог 1, %"
                       className="px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
                <input type="number" value={form.bonus1}
                       onChange={(e) => setForm({ ...form, bonus1: e.target.value })}
                       placeholder="Бонус 1, ₽"
                       className="px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
                <input type="number" value={form.threshold2}
                       onChange={(e) => setForm({ ...form, threshold2: e.target.value })}
                       placeholder="Порог 2, %"
                       className="px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
                <input type="number" value={form.bonus2}
                       onChange={(e) => setForm({ ...form, bonus2: e.target.value })}
                       placeholder="Бонус 2, ₽"
                       className="px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
              </div>
            )}
            <Button onClick={() => create.mutate()}
                    disabled={!form.manager || !form.target}
                    className="mt-3">
              + Назначить KPI
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
                      <div className={cn('w-8 h-8 rounded-full inline-flex items-center justify-center font-bold text-sm',
                        idx === 0 ? 'bg-yellow-100 text-yellow-700' :
                        idx === 1 ? 'bg-slate-100 text-slate-700' :
                        idx === 2 ? 'bg-orange-100 text-orange-700' : 'bg-bg-subtle text-fg-muted')}>
                        {idx + 1}
                      </div>
                      <div className="flex-1">
                        <div className="font-medium text-fg">{k.manager_name}</div>
                        <div className="text-xs text-fg-muted">
                          Цель {k.target_value.toLocaleString('ru-RU')} {k.metric_code}
                          {k.bonus_rule?.model === 'A' && ` · ${k.bonus_rule.pct_of_net}% от чистой`}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={cn('text-lg font-semibold tabular-nums',
                          tone === 'emerald' && 'text-emerald-700',
                          tone === 'amber' && 'text-amber-700',
                          tone === 'rose' && 'text-rose-700')}>
                          {k.completionPct.toFixed(0)}%
                        </div>
                      </div>
                      <button onClick={() => {
                        if (confirm(`Удалить «${k.manager_name}»?`)) remove.mutate(k.id)
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


// ===========================================
// GAME MODE — спидометр + уровни + темп
// ===========================================

function GameTab() {
  const { data: plans = [] } = useQuery<PlanRow[]>({
    queryKey: ['plans'],
    queryFn: async () => (await api.get('/plans')).data,
  })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { data: fact } = useQuery<any>({
    queryKey: ['plan-fact', selectedId],
    queryFn: async () => (await api.get(`/plans/${selectedId}/fact`)).data,
    enabled: !!selectedId,
  })
  const [tempRate, setTempRate] = useState<number | null>(null)

  if (plans.length === 0) {
    return <Card className="p-8 text-center text-fg-muted">Создай план сначала.</Card>
  }

  // Спидометр: 0…120% pro-rata
  const completion = fact?.completion_prorata_pct || 0
  const zone = completion >= 110 ? 'blue'
             : completion >= 95 ? 'green'
             : completion >= 70 ? 'amber' : 'red'
  const level = completion >= 110 ? 'Газ в пол 🚀'
             : completion >= 95 ? 'В цель 🎯'
             : completion >= 70 ? 'Разгон ⚡' : 'Прокол 🔧'

  // Текущий темп (фact/day)
  const currentRate = fact?.days_elapsed > 0
    ? Math.round(fact.fact_value / fact.days_elapsed) : 0
  const targetRate = fact?.needed_per_day || 0
  const userRate = tempRate ?? currentRate
  const projection = fact?.days_elapsed > 0 && fact?.days_total
    ? fact.fact_value + (userRate * fact.days_remaining)
    : 0
  const projCompletion = fact?.plan_value > 0
    ? (projection / fact.plan_value) * 100 : 0

  return (
    <div className="space-y-4">
      <Card className="p-3">
        <label className="text-xs text-fg-muted block mb-1">План</label>
        <select value={selectedId || ''} onChange={(e) => setSelectedId(e.target.value || null)}
                className="w-full md:w-96 px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg">
          <option value="">— выбери план —</option>
          {plans.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </Card>

      {fact && (
        <>
          {/* Spidometer + Level */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card className="p-6 flex flex-col items-center">
              <div className="text-xs text-fg-muted uppercase tracking-wide">Спидометр</div>
              <Speedometer percentage={Math.min(140, completion)} zone={zone} />
              <div className={cn('text-3xl font-bold tabular-nums mt-2',
                zone === 'blue' && 'text-blue-700',
                zone === 'green' && 'text-emerald-700',
                zone === 'amber' && 'text-amber-700',
                zone === 'red' && 'text-rose-700')}>
                {completion.toFixed(0)}%
              </div>
              <div className="text-xs text-fg-muted">от темпа плана</div>
            </Card>

            <Card className="p-6">
              <div className="text-xs text-fg-muted uppercase tracking-wide">Уровень</div>
              <div className="text-2xl font-bold mt-1">{level}</div>
              <div className="mt-4 space-y-2">
                {['Прокол', 'Разгон', 'В цель', 'Газ в пол'].map((l, i) => {
                  const at = [0, 70, 95, 110][i]
                  const active = completion >= at && (i === 3 || completion < [70, 95, 110, Infinity][i])
                  return (
                    <div key={l} className="flex items-center gap-3">
                      <div className={cn('w-2 h-2 rounded-full',
                        active ? 'bg-purple-600' : 'bg-bg-subtle')} />
                      <div className={cn('text-sm', active ? 'font-semibold text-fg' : 'text-fg-muted')}>
                        {l} ({at}%+)
                      </div>
                    </div>
                  )
                })}
              </div>
              <div className="mt-4 text-xs text-fg-muted">
                Дней осталось: <b className="text-fg">{fact.days_remaining}</b>{' '}
                · Текущий темп: <b className="text-fg tabular-nums">
                  {currentRate.toLocaleString('ru-RU')}/день
                </b>
              </div>
            </Card>
          </div>

          {/* Темп-слайдер */}
          <Card className="p-5">
            <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-500" />
              Темп-слайдер: «а если буду делать X/день?»
            </h3>
            <div className="space-y-3">
              <input type="range" min={0} max={Math.max(targetRate * 2, currentRate * 2, 1)}
                     step={1} value={userRate}
                     onChange={(e) => setTempRate(Number(e.target.value))}
                     className="w-full" />
              <div className="grid grid-cols-3 gap-3 text-sm">
                <Card className="p-3 bg-bg-subtle/30">
                  <div className="text-xs text-fg-muted">Темп</div>
                  <div className="text-lg font-semibold tabular-nums">
                    {userRate.toLocaleString('ru-RU')}/день
                  </div>
                </Card>
                <Card className="p-3 bg-bg-subtle/30">
                  <div className="text-xs text-fg-muted">К концу периода</div>
                  <div className="text-lg font-semibold tabular-nums">
                    {Math.round(projection).toLocaleString('ru-RU')}
                  </div>
                </Card>
                <Card className={cn('p-3',
                  projCompletion >= 100 ? 'bg-emerald-50/40' : 'bg-amber-50/40')}>
                  <div className="text-xs text-fg-muted">Будет % выполнения</div>
                  <div className={cn('text-lg font-bold tabular-nums',
                    projCompletion >= 100 ? 'text-emerald-700' : 'text-amber-700')}>
                    {projCompletion.toFixed(0)}%
                  </div>
                </Card>
              </div>
              <div className="text-xs text-fg-muted">
                💡 Нужно <b className="text-fg">{Math.round(targetRate).toLocaleString('ru-RU')}/день</b>,
                чтобы добежать до плана.
              </div>
            </div>
          </Card>

          {/* Достижения */}
          <Card className="p-4">
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <Trophy className="w-4 h-4 text-yellow-500" />
              Достижения
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
              <Badge label="Стартовал" earned={true} />
              <Badge label="70% pro-rata" earned={completion >= 70} />
              <Badge label="В цель (95%)" earned={completion >= 95} />
              <Badge label="Сверх плана" earned={completion >= 110} />
            </div>
          </Card>
        </>
      )}
    </div>
  )
}


function Speedometer({ percentage, zone }: { percentage: number; zone: string }) {
  // Полукруг 0..180°. 100% pro-rata = 150° (centered), 140% = 180°.
  const angle = Math.min(180, (percentage / 140) * 180)
  const color = zone === 'blue' ? '#3b82f6'
              : zone === 'green' ? '#10b981'
              : zone === 'amber' ? '#f59e0b' : '#ef4444'
  return (
    <svg width="220" height="130" viewBox="0 0 220 130" className="mt-3">
      {/* Background arcs by zone */}
      <path d="M 20 110 A 90 90 0 0 1 50 35" stroke="#ef4444" strokeWidth="14" fill="none" />
      <path d="M 50 35 A 90 90 0 0 1 110 20" stroke="#f59e0b" strokeWidth="14" fill="none" />
      <path d="M 110 20 A 90 90 0 0 1 170 35" stroke="#10b981" strokeWidth="14" fill="none" />
      <path d="M 170 35 A 90 90 0 0 1 200 110" stroke="#3b82f6" strokeWidth="14" fill="none" />
      {/* Needle */}
      <g transform={`translate(110 110) rotate(${angle - 90})`}>
        <line x1="0" y1="0" x2="0" y2="-85" stroke={color} strokeWidth="3" strokeLinecap="round" />
        <circle cx="0" cy="0" r="6" fill={color} />
      </g>
    </svg>
  )
}


function Badge({ label, earned }: { label: string; earned: boolean }) {
  return (
    <div className={cn('px-2 py-1.5 rounded border text-center',
      earned ? 'bg-yellow-50 border-yellow-300 text-yellow-800'
             : 'bg-bg-subtle border-border-subtle text-fg-subtle')}>
      {earned ? '🏆 ' : '🔒 '}{label}
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
        tone === 'rose' && 'text-rose-700')}>{value}</div>
      {subtitle && <div className="text-[10px] text-fg-muted mt-0.5">{subtitle}</div>}
    </Card>
  )
}
