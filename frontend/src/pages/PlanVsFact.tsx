import { useState, useMemo, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Lock, LockOpen, Download, RotateCcw, ChevronRight,
  Loader2, Target, CheckCircle2, Plus, Users2, X,
} from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Legend,
  BarChart, Bar, Cell, LabelList,
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
type Tab = 'plan' | 'fact' | 'kpi' | 'game'
type Step = 1 | 2 | 3

const METRIC_LABELS: Record<Metric, string> = {
  orders: 'Заказы (шт)',
  revenue: 'Выручка',
  marginal_profit: 'Маржинальная прибыль',
}

function isMoney(m: string) {
  return m === 'revenue' || m === 'marginal_profit' || m === 'margin' || m === 'returns'
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
  pro_rata: number | null
  pct: number | null
  run_rate: number | null
}

interface FactResp {
  plan_id: string | null
  period_from: string
  period_to: string
  total_days: number
  days_passed: number
  rows: FactRow[]
}

interface BridgeItem {
  label: string
  value: number
  pct: number
  estimated: boolean
  color: 'positive' | 'negative' | 'neutral'
}

interface BridgeResp {
  base: number
  actual: number
  delta: number
  items: BridgeItem[]
  check_delta: number
}

interface DailyFactDay {
  date: string
  plan: number
  fact: number
  green: boolean
}

interface DailyFactResp {
  days: DailyFactDay[]
  streak: number
}

interface TeamMember {
  id: string
  user_id: string
  email: string
  full_name: string | null
  role: string
  status: string
}

type BonusRule =
  | { type: 'pct_profit'; pct: number }
  | { type: 'threshold'; thresholds: { pct: number; bonus: number }[] }

interface KpiItem {
  id: number
  manager_id: string | null
  manager_name: string | null
  metric_code: string
  target_value: number | null
  fact_value: number
  pct: number | null
  forecast_value: number | null
  estimated_bonus: number | null
  bonus_rule: BonusRule | null
}

const KPI_METRIC_OPTS = [
  { value: 'orders',  label: 'Заказы' },
  { value: 'revenue', label: 'Выручка' },
  { value: 'margin',  label: 'Маржинальная прибыль' },
]

const KPI_METRIC_LABEL: Record<string, string> = {
  orders:          'Заказы',
  revenue:         'Выручка',
  margin:          'Маржинальная прибыль',
  marginal_profit: 'Маржинальная прибыль',
  returns:         'Возвраты',
}

// ── Fact date formatter ───────────────────────────────────────────────

function fmtFactDate(iso: string) {
  const d = new Date(iso + 'T00:00:00')
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.${d.getFullYear()}`
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

// ── KPI Modal ─────────────────────────────────────────────────────────

type BonusModel = 'A' | 'B'

function KpiModal({
  planId,
  members,
  onClose,
  onSaved,
}: {
  planId: string
  members: TeamMember[]
  onClose: () => void
  onSaved: () => void
}) {
  const [managerId, setManagerId]   = useState('')
  const [metricCode, setMetricCode] = useState('orders')
  const [targetValue, setTargetValue] = useState('')
  const [bonusModel, setBonusModel] = useState<BonusModel>('B')
  const [bonusPct, setBonusPct]     = useState('5')
  const [thresholds, setThresholds] = useState([
    { pct: '80', bonus: '5000' },
    { pct: '100', bonus: '15000' },
  ])

  const addKpi = useMutation({
    mutationFn: async () => {
      const bonus_rule: BonusRule =
        bonusModel === 'A'
          ? { type: 'pct_profit', pct: parseFloat(bonusPct) || 0 }
          : {
              type: 'threshold',
              thresholds: thresholds
                .map((t) => ({ pct: parseFloat(t.pct) || 0, bonus: parseFloat(t.bonus) || 0 }))
                .filter((t) => t.pct > 0),
            }
      return (await api.post(`/plan/sales/${planId}/kpi`, {
        manager_id:   managerId || null,
        metric_code:  metricCode,
        target_value: parseFloat(targetValue) || 0,
        bonus_rule,
      })).data
    },
    onSuccess: () => onSaved(),
  })

  const addThreshold = () =>
    setThresholds((p) => [...p, { pct: '', bonus: '' }])

  const removeThreshold = (i: number) =>
    setThresholds((p) => p.filter((_, idx) => idx !== i))

  const updateThreshold = (i: number, field: 'pct' | 'bonus', val: string) =>
    setThresholds((p) => p.map((t, idx) => (idx === i ? { ...t, [field]: val } : t)))

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <Card
        className="max-w-lg w-full p-5 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-fg">Назначить KPI</h2>
          <button onClick={onClose} className="text-fg-muted hover:text-fg">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-4 text-sm">
          {/* Менеджер */}
          <div>
            <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">
              Менеджер
            </label>
            <select
              value={managerId}
              onChange={(e) => setManagerId(e.target.value)}
              className="h-9 px-3 rounded-md border border-border bg-surface text-sm w-full"
            >
              <option value="">— Без менеджера —</option>
              {members.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.full_name || m.email}
                </option>
              ))}
            </select>
          </div>

          {/* Метрика */}
          <div>
            <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">
              Метрика
            </label>
            <select
              value={metricCode}
              onChange={(e) => setMetricCode(e.target.value)}
              className="h-9 px-3 rounded-md border border-border bg-surface text-sm w-full"
            >
              {KPI_METRIC_OPTS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {/* Цель */}
          <div>
            <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">
              Цель
            </label>
            <Input
              type="number"
              value={targetValue}
              onChange={(e) => setTargetValue(e.target.value)}
              placeholder={isMoney(metricCode) ? 'напр. 500 000' : 'напр. 200'}
              className="w-full"
            />
          </div>

          {/* Модель мотивации */}
          <div className="border border-border-subtle rounded-md p-3 space-y-3">
            <p className="text-[11px] font-medium text-fg-muted uppercase">Модель мотивации</p>
            <div className="flex gap-2">
              {(['A', 'B'] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setBonusModel(m)}
                  className={cn(
                    'flex-1 px-3 py-2 rounded border text-sm font-medium',
                    bonusModel === m
                      ? 'border-fg bg-fg text-bg'
                      : 'border-border-subtle text-fg-muted hover:bg-bg-subtle',
                  )}
                >
                  {m === 'A' ? 'A: % от метрики' : 'B: Пороговая'}
                </button>
              ))}
            </div>

            {bonusModel === 'A' && (
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  value={bonusPct}
                  onChange={(e) => setBonusPct(e.target.value)}
                  className="w-24"
                  placeholder="5"
                />
                <span className="text-fg-muted text-sm">% от значения метрики</span>
              </div>
            )}

            {bonusModel === 'B' && (
              <div className="space-y-2">
                <div className="grid grid-cols-[1fr_1fr_auto] gap-2 text-[11px] font-medium text-fg-muted uppercase">
                  <span>% выполнения ≥</span>
                  <span>Бонус, ₽</span>
                  <span />
                </div>
                {thresholds.map((t, i) => (
                  <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-2 items-center">
                    <Input
                      type="number"
                      value={t.pct}
                      onChange={(e) => updateThreshold(i, 'pct', e.target.value)}
                      placeholder="80"
                    />
                    <Input
                      type="number"
                      value={t.bonus}
                      onChange={(e) => updateThreshold(i, 'bonus', e.target.value)}
                      placeholder="5000"
                    />
                    <button
                      type="button"
                      onClick={() => removeThreshold(i)}
                      className="text-fg-muted hover:text-rose-600 px-1"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={addThreshold}
                  className="text-xs text-blue-600 hover:underline"
                >
                  + Добавить порог
                </button>
              </div>
            )}
          </div>

          {addKpi.isError && (
            <div className="text-sm text-rose-700 bg-rose-50 px-3 py-2 rounded">
              Ошибка при сохранении. Проверьте данные.
            </div>
          )}
        </div>

        <div className="flex gap-2 mt-5 justify-end">
          <Button variant="ghost" onClick={onClose}>Отмена</Button>
          <Button
            onClick={() => addKpi.mutate()}
            disabled={addKpi.isPending || !targetValue}
          >
            {addKpi.isPending
              ? <Loader2 className="w-4 h-4 animate-spin" />
              : 'Сохранить'}
          </Button>
        </div>
      </Card>
    </div>
  )
}

// ── Bridge waterfall ──────────────────────────────────────────────────

type WEntry = {
  name: string
  start: number
  value: number
  raw: number
  fill: string
  estimated: boolean
}

function BridgeWaterfall({ bridge }: { bridge: BridgeResp }) {
  const data = useMemo<WEntry[]>(() => {
    const entries: WEntry[] = []
    entries.push({ name: 'План', start: 0, value: bridge.base, raw: bridge.base, fill: '#94a3b8', estimated: false })
    let cursor = bridge.base
    bridge.items.forEach((item) => {
      const bottom = item.value >= 0 ? cursor : cursor + item.value
      entries.push({
        name: item.label,
        start: bottom,
        value: Math.abs(item.value),
        raw: item.value,
        fill: item.color === 'positive' ? '#10b981' : item.color === 'negative' ? '#ef4444' : '#94a3b8',
        estimated: item.estimated,
      })
      cursor += item.value
    })
    entries.push({ name: 'Факт', start: 0, value: bridge.actual, raw: bridge.actual, fill: '#3b82f6', estimated: false })
    return entries
  }, [bridge])

  return (
    <Card className="p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-fg">Разложение отклонения выручки</p>
        {Math.abs(bridge.check_delta) > 100 && (
          <span className="text-xs text-amber-600">невязка {formatCurrency(bridge.check_delta)}</span>
        )}
      </div>

      <div className="h-[240px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle, #e5e7eb)" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 10, fill: 'var(--fg-muted, #6b7280)' }}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: 'var(--fg-muted, #6b7280)' }}
              tickLine={false}
              tickFormatter={(v: number) => `${Math.round(v / 1000)}к`}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const e = payload[0].payload as WEntry
                return (
                  <div style={{
                    background: 'var(--surface, #fff)',
                    border: '1px solid var(--border, #e5e7eb)',
                    borderRadius: 6,
                    padding: '6px 10px',
                    fontSize: 12,
                  }}>
                    <p style={{ fontWeight: 500, marginBottom: 2 }}>{e.name}</p>
                    <p>{formatCurrency(e.raw)}</p>
                    {e.estimated && <p style={{ color: '#d97706', fontSize: 11, marginTop: 2 }}>оценочно</p>}
                  </div>
                )
              }}
            />
            <Bar dataKey="start" stackId="w" fill="transparent" isAnimationActive={false} />
            <Bar dataKey="value" stackId="w" isAnimationActive={false} radius={[3, 3, 0, 0]}>
              {data.map((e, i) => (
                <Cell key={i} fill={e.fill} fillOpacity={e.estimated ? 0.4 : 1} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <table className="w-full text-sm">
        <thead className="border-b border-border-subtle">
          <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
            <th className="pb-2 font-medium">Эффект</th>
            <th className="pb-2 px-4 font-medium text-right">Сумма</th>
            <th className="pb-2 font-medium text-right">% от Δ</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {bridge.items.map((item) => (
            <tr key={item.label} className="hover:bg-bg-subtle/40">
              <td className="py-2">
                <span className="flex items-center gap-2">
                  {item.label}
                  {item.estimated && (
                    <span className="text-[10px] text-amber-600 bg-amber-50 border border-amber-200 rounded px-1 py-0.5">
                      оценочно
                    </span>
                  )}
                </span>
              </td>
              <td className={cn(
                'py-2 px-4 text-right tabular-nums font-medium',
                item.color === 'positive' ? 'text-emerald-700' :
                item.color === 'negative' ? 'text-rose-700' : 'text-fg-muted',
              )}>
                {item.value >= 0 ? '+' : ''}{formatCurrency(item.value)}
              </td>
              <td className="py-2 text-right tabular-nums text-fg-muted">
                {item.pct >= 0 ? '+' : ''}{item.pct.toFixed(1)}%
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot className="border-t-2 border-border">
          <tr className="font-semibold text-sm">
            <td className="pt-2.5 text-fg-muted">Δ выручка</td>
            <td className={cn(
              'pt-2.5 px-4 text-right tabular-nums',
              bridge.delta >= 0 ? 'text-emerald-700' : 'text-rose-700',
            )}>
              {bridge.delta >= 0 ? '+' : ''}{formatCurrency(bridge.delta)}
            </td>
            <td className="pt-2.5 text-right tabular-nums text-fg-muted">100%</td>
          </tr>
        </tfoot>
      </table>
    </Card>
  )
}

// ── Gauge (спидометр) ────────────────────────────────────────────────

const GAUGE_MAX = 150 // % — правый край шкалы
const CX = 150, CY = 150, R_OUTER = 125, R_INNER = 82

function pctToAngle(pct: number): number {
  // 0% → 180° (левый), GAUGE_MAX% → 0° (правый), по верхней дуге
  return 180 - (Math.min(pct, GAUGE_MAX) / GAUGE_MAX) * 180
}

function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = (angleDeg * Math.PI) / 180
  return { x: cx + r * Math.cos(rad), y: cy - r * Math.sin(rad) }
}

function arcPath(a1: number, a2: number): string {
  // Сегмент «пончика» от угла a1 до a2 (a1 > a2)
  const large = a1 - a2 > 180 ? 1 : 0
  const o1 = polar(CX, CY, R_OUTER, a1)
  const o2 = polar(CX, CY, R_OUTER, a2)
  const i1 = polar(CX, CY, R_INNER, a1)
  const i2 = polar(CX, CY, R_INNER, a2)
  return [
    `M ${o1.x.toFixed(2)} ${o1.y.toFixed(2)}`,
    `A ${R_OUTER} ${R_OUTER} 0 ${large} 0 ${o2.x.toFixed(2)} ${o2.y.toFixed(2)}`,
    `L ${i2.x.toFixed(2)} ${i2.y.toFixed(2)}`,
    `A ${R_INNER} ${R_INNER} 0 ${large} 1 ${i1.x.toFixed(2)} ${i1.y.toFixed(2)}`,
    'Z',
  ].join(' ')
}

const GAUGE_ZONES = [
  { from: 0,   to: 80,       color: '#f87171' }, // красная
  { from: 80,  to: 100,      color: '#fbbf24' }, // жёлтая
  { from: 100, to: 120,      color: '#34d399' }, // зелёная
  { from: 120, to: GAUGE_MAX, color: '#60a5fa' }, // синяя
]

function GaugeChart({ pct }: { pct: number }) {
  const status =
    pct < 80  ? { label: 'Прокол',    color: '#f87171' } :
    pct < 100 ? { label: 'Разгон',    color: '#fbbf24' } :
    pct < 120 ? { label: 'В цель',    color: '#34d399' } :
                { label: 'Газ в пол', color: '#60a5fa' }

  const needleAngle = pctToAngle(pct)
  const needleTip = polar(CX, CY, R_OUTER - 8, needleAngle)

  return (
    <div className="flex flex-col items-center gap-2">
      <svg viewBox="0 0 300 160" className="w-full max-w-[300px]">
        {GAUGE_ZONES.map((z) => (
          <path
            key={z.from}
            d={arcPath(pctToAngle(z.from), pctToAngle(z.to))}
            fill={z.color}
            fillOpacity={0.85}
          />
        ))}
        {/* Zone labels */}
        {[
          { pct: 40,  label: '0%' },
          { pct: 90,  label: '80%' },
          { pct: 110, label: '100%' },
          { pct: 135, label: '120%' },
        ].map(({ pct: p, label }) => {
          const pt = polar(CX, CY, R_OUTER + 12, pctToAngle(p))
          return (
            <text key={label} x={pt.x} y={pt.y} textAnchor="middle" fontSize="9"
              fill="#9ca3af" dominantBaseline="middle">{label}</text>
          )
        })}
        {/* Needle */}
        <line
          x1={CX} y1={CY}
          x2={needleTip.x.toFixed(2)} y2={needleTip.y.toFixed(2)}
          stroke="#1f2937" strokeWidth="3" strokeLinecap="round"
        />
        <circle cx={CX} cy={CY} r="6" fill="#1f2937" />
      </svg>
      <div className="text-center -mt-2">
        <div className="text-4xl font-bold tabular-nums" style={{ color: status.color }}>
          {pct.toFixed(1)}%
        </div>
        <div className="text-sm font-medium mt-1" style={{ color: status.color }}>
          {status.label}
        </div>
      </div>
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

  // KPI modal
  const [kpiModalOpen, setKpiModalOpen] = useState(false)

  // Game mode
  const [sliderPace, setSliderPace] = useState<number | null>(null)

  const qc = useQueryClient()

  // Cabinets
  const { data: cabinets = [] } = useQuery<OzonAccountSummary[]>({
    queryKey: ['ozon-accounts'],
    queryFn: async () => (await api.get('/ozon-accounts/')).data,
    staleTime: 60_000,
  })

  // Plan list (for Fact + KPI + Game tabs)
  const { data: planList = [] } = useQuery<PlanListItem[]>({
    queryKey: ['plan-sales-list'],
    queryFn: async () => (await api.get('/plan/sales')).data,
    enabled: tab === 'fact' || tab === 'kpi' || tab === 'game',
  })

  const activePlanId = savedPlanId ?? planList[0]?.id ?? null

  // Team members (for KPI modal)
  const { data: teamMembers = [] } = useQuery<TeamMember[]>({
    queryKey: ['team-members'],
    queryFn: async () => (await api.get('/team/members')).data,
    enabled: tab === 'kpi',
    staleTime: 60_000,
  })

  // KPI list
  const { data: kpiList = [], refetch: refetchKpi } = useQuery<KpiItem[]>({
    queryKey: ['plan-kpi', activePlanId],
    queryFn: async () => (await api.get(`/plan/sales/${activePlanId}/kpi`)).data,
    enabled: (tab === 'kpi' || tab === 'game') && !!activePlanId,
  })

  // Fact data — с планом (если план есть)
  const { data: planFact, isLoading: planFactLoading } = useQuery<FactResp>({
    queryKey: ['plan-fact', activePlanId],
    queryFn: async () => (await api.get(`/plan/sales/${activePlanId}/fact`)).data,
    enabled: (tab === 'fact' || tab === 'game') && !!activePlanId,
  })

  // Fact data — без плана: MTD текущего месяца
  const { data: currentFact, isLoading: currentFactLoading } = useQuery<FactResp>({
    queryKey: ['current-fact'],
    queryFn: async () => (await api.get('/plan/sales/current-fact')).data,
    enabled: (tab === 'fact' || tab === 'game') && !activePlanId,
  })

  const fact = planFact ?? currentFact
  const factLoading = planFactLoading || currentFactLoading

  // Bridge waterfall
  const { data: bridge } = useQuery<BridgeResp>({
    queryKey: ['plan-bridge', activePlanId],
    queryFn: async () => (await api.get(`/plan/sales/${activePlanId}/bridge`)).data,
    enabled: tab === 'fact' && !!activePlanId,
  })

  // Daily fact (game tab)
  const { data: dailyFact } = useQuery<DailyFactResp>({
    queryKey: ['plan-daily-fact', activePlanId],
    queryFn: async () => (await api.get(`/plan/sales/${activePlanId}/daily-fact`)).data,
    enabled: tab === 'game' && !!activePlanId,
  })

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
      <div className="flex gap-2 flex-wrap">
        {(['plan', 'fact', 'kpi', 'game'] as const).map((t) => (
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
            {t === 'plan' ? 'Постановка плана' :
             t === 'fact' ? 'Факт' :
             t === 'kpi'  ? 'KPI команды' :
                            'Игровой режим'}
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
                <p className="text-sm font-medium text-fg">
                  {fmtFactDate(fact.period_from)} — {fmtFactDate(fact.period_to)}{' '}
                  <span className="text-fg-muted font-normal">
                    ({fact.days_passed} из {fact.total_days} дней)
                  </span>
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
                    <th className="py-2.5 px-4 font-medium text-right">Прогноз</th>
                    <th className="py-2.5 px-4 font-medium text-right">% к темпу</th>
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
                      <td className="py-3 px-4 text-right tabular-nums text-blue-600">
                        {r.run_rate != null ? fmtVal(r.run_rate, r.metric) : '—'}
                      </td>
                      <td className="py-3 px-4 text-right">
                        {r.pct != null ? (
                          <span className={cn(
                            'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
                            r.pct >= 100 ? 'bg-emerald-50 text-emerald-700' :
                            r.pct >= 80  ? 'bg-amber-50 text-amber-700' :
                                           'bg-rose-50 text-rose-700',
                          )}>
                            {r.pct >= 100 ? '🟢' : r.pct >= 80 ? '🟡' : '🔴'} {r.pct.toFixed(1)}%
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-400">
                            ⚪ —
                          </span>
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

          {bridge && <BridgeWaterfall bridge={bridge} />}
        </>
      )}

      {/* ═══ KPI TAB ═══ */}
      {tab === 'kpi' && (
        <>
          {!activePlanId ? (
            <Card className="py-14 flex flex-col items-center gap-3 text-fg-muted">
              <Users2 className="w-8 h-8 text-fg-subtle" />
              <p className="text-sm">Сначала поставьте план</p>
              <Button size="sm" variant="ghost" onClick={() => setTab('plan')}>
                Перейти к постановке плана →
              </Button>
            </Card>
          ) : (
            <>
              {/* Header */}
              <div className="flex items-center justify-between">
                <p className="text-sm text-fg-muted">KPI команды по текущему плану</p>
                <Button size="sm" onClick={() => setKpiModalOpen(true)}>
                  <Plus className="w-4 h-4" /> Назначить KPI
                </Button>
              </div>

              {/* KPI table */}
              {kpiList.length > 0 ? (
                <Card className="overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                        <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                          <th className="py-2.5 px-4 font-medium">Менеджер</th>
                          <th className="py-2.5 px-4 font-medium">Метрика</th>
                          <th className="py-2.5 px-4 font-medium text-right">Цель</th>
                          <th className="py-2.5 px-4 font-medium text-right">Факт</th>
                          <th className="py-2.5 px-4 font-medium text-right">%</th>
                          <th className="py-2.5 px-4 font-medium text-right">Прогноз</th>
                          <th className="py-2.5 px-4 font-medium text-right">Бонус</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border-subtle">
                        {kpiList.map((kpi) => (
                          <tr key={kpi.id} className="hover:bg-bg-subtle/40">
                            <td className="py-3 px-4 font-medium text-fg">
                              {kpi.manager_name ?? (
                                <span className="text-fg-subtle italic text-xs">Без менеджера</span>
                              )}
                            </td>
                            <td className="py-3 px-4 text-fg-muted">
                              {KPI_METRIC_LABEL[kpi.metric_code] ?? kpi.metric_code}
                            </td>
                            <td className="py-3 px-4 text-right tabular-nums text-fg-muted">
                              {kpi.target_value != null ? fmtVal(kpi.target_value, kpi.metric_code) : '—'}
                            </td>
                            <td className="py-3 px-4 text-right tabular-nums text-fg">
                              {fmtVal(kpi.fact_value, kpi.metric_code)}
                            </td>
                            <td className="py-3 px-4 text-right">
                              {kpi.pct != null ? (
                                <span className={cn(
                                  'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
                                  kpi.pct >= 100 ? 'bg-emerald-50 text-emerald-700' :
                                  kpi.pct >= 80  ? 'bg-amber-50 text-amber-700' :
                                                   'bg-rose-50 text-rose-700',
                                )}>
                                  {kpi.pct >= 100 ? '🟢' : kpi.pct >= 80 ? '🟡' : '🔴'}{' '}
                                  {kpi.pct.toFixed(1)}%
                                </span>
                              ) : (
                                <span className="text-fg-subtle text-xs">—</span>
                              )}
                            </td>
                            <td className="py-3 px-4 text-right tabular-nums text-blue-600">
                              {kpi.forecast_value != null
                                ? fmtVal(kpi.forecast_value, kpi.metric_code)
                                : '—'}
                            </td>
                            <td className="py-3 px-4 text-right tabular-nums font-medium text-emerald-700">
                              {kpi.estimated_bonus != null
                                ? formatCurrency(kpi.estimated_bonus)
                                : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              ) : (
                <Card className="py-10 flex flex-col items-center gap-2 text-fg-muted">
                  <p className="text-sm">KPI ещё не назначены</p>
                  <Button size="sm" variant="ghost" onClick={() => setKpiModalOpen(true)}>
                    Назначить первый KPI →
                  </Button>
                </Card>
              )}

              {/* Rating (≥2 строки с pct) */}
              {kpiList.filter((k) => k.pct != null).length >= 2 && (() => {
                const ratingData = [...kpiList]
                  .filter((k) => k.pct != null)
                  .sort((a, b) => (b.pct ?? 0) - (a.pct ?? 0))
                  .map((k, i) => ({
                    name: k.manager_name
                      ? `${i + 1}. ${k.manager_name}`
                      : `${i + 1}. ${KPI_METRIC_LABEL[k.metric_code] ?? k.metric_code}`,
                    pct: k.pct!,
                  }))
                const chartH = Math.max(120, ratingData.length * 44)
                return (
                  <Card className="p-5 flex flex-col gap-3">
                    <p className="text-sm font-medium text-fg">Рейтинг выполнения</p>
                    <div style={{ height: chartH }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          layout="vertical"
                          data={ratingData}
                          margin={{ top: 4, right: 64, left: 8, bottom: 4 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle, #e5e7eb)" horizontal={false} />
                          <XAxis
                            type="number"
                            domain={[0, Math.max(100, ...ratingData.map((r) => r.pct))]}
                            tickFormatter={(v: number) => `${v}%`}
                            tick={{ fontSize: 10, fill: 'var(--fg-muted, #6b7280)' }}
                            tickLine={false}
                          />
                          <YAxis
                            type="category"
                            dataKey="name"
                            tick={{ fontSize: 11, fill: 'var(--fg-muted, #6b7280)' }}
                            width={160}
                            tickLine={false}
                          />
                          <Bar dataKey="pct" isAnimationActive={false} radius={[0, 3, 3, 0]}>
                            {ratingData.map((entry, idx) => (
                              <Cell
                                key={idx}
                                fill={
                                  entry.pct >= 100 ? '#10b981' :
                                  entry.pct >= 80  ? '#f59e0b' : '#ef4444'
                                }
                              />
                            ))}
                            <LabelList
                              dataKey="pct"
                              position="right"
                              formatter={(v: number) => `${v.toFixed(1)}%`}
                              style={{ fontSize: 11, fill: 'var(--fg-muted, #6b7280)' }}
                            />
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </Card>
                )
              })()}
            </>
          )}

          {kpiModalOpen && activePlanId && (
            <KpiModal
              planId={String(activePlanId)}
              members={teamMembers}
              onClose={() => setKpiModalOpen(false)}
              onSaved={() => {
                setKpiModalOpen(false)
                qc.invalidateQueries({ queryKey: ['plan-kpi', activePlanId] })
              }}
            />
          )}
        </>
      )}

      {/* ═══ GAME TAB ═══ */}
      {tab === 'game' && (() => {
        if (!activePlanId) {
          return (
            <Card className="py-14 flex flex-col items-center gap-3 text-fg-muted">
              <Target className="w-8 h-8 text-fg-subtle" />
              <p className="text-sm">Сначала поставьте план</p>
              <Button size="sm" variant="ghost" onClick={() => setTab('plan')}>
                Перейти к постановке плана →
              </Button>
            </Card>
          )
        }

        // Берём первую метрику с планом (или первую вообще)
        const primaryRow = fact?.rows.find((r) => r.pct != null) ?? fact?.rows[0] ?? null
        const gaugePct = primaryRow?.pct ?? 0
        const factVal = primaryRow?.fact ?? 0
        const planVal = primaryRow?.plan ?? 0
        const daysPassed = fact?.days_passed ?? 0
        const totalDays = fact?.total_days ?? 1
        const remainingDays = Math.max(totalDays - daysPassed, 0)

        // Текущий темп в день
        const currentPace = daysPassed > 0 ? factVal / daysPassed : 0
        const sliderMax = Math.max(Math.round(currentPace * 2), 1)
        const pace = sliderPace ?? Math.round(currentPace)

        // Прогноз по слайдеру
        const projectedTotal = factVal + pace * remainingDays

        // Нужный темп для выполнения плана
        const neededPace = remainingDays > 0 && planVal > factVal
          ? Math.ceil((planVal - factVal) / remainingDays)
          : null

        // Прогресс-бар: факт к плану
        const progressPct = planVal > 0 ? Math.min((factVal / planVal) * 100, 100) : 0

        // Рейтинг из KPI
        const ratingData = [...kpiList]
          .filter((k) => k.pct != null)
          .sort((a, b) => (b.pct ?? 0) - (a.pct ?? 0))

        return (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

            {/* БЛОК 1 — Спидометр */}
            <Card className="p-5 flex flex-col gap-4">
              <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">
                Выполнение к темпу
              </p>
              {primaryRow ? (
                <GaugeChart pct={gaugePct} />
              ) : (
                <p className="text-sm text-fg-muted text-center py-8">Нет данных</p>
              )}
            </Card>

            {/* БЛОК 2 — Темп-слайдер */}
            <Card className="p-5 flex flex-col gap-4">
              <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">
                Симулятор темпа
              </p>
              {primaryRow ? (
                <>
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-fg-muted">
                        {isMoney(primaryRow.metric) ? 'Выручка/день' : 'Шт/день'}
                      </span>
                      <span className="font-semibold tabular-nums text-fg">
                        {isMoney(primaryRow.metric) ? formatCurrency(pace) : formatNumber(pace)}
                      </span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={sliderMax}
                      step={isMoney(primaryRow.metric) ? 1000 : 1}
                      value={pace}
                      onChange={(e) => setSliderPace(Number(e.target.value))}
                      className="w-full accent-fg"
                    />
                    <div className="flex justify-between text-[10px] text-fg-muted">
                      <span>0</span>
                      <span>{isMoney(primaryRow.metric) ? formatCurrency(currentPace) : formatNumber(currentPace)} текущий</span>
                      <span>{isMoney(primaryRow.metric) ? formatCurrency(sliderMax) : formatNumber(sliderMax)}</span>
                    </div>
                  </div>

                  <div className="bg-bg-subtle rounded-md px-4 py-3 space-y-1.5 text-sm">
                    <div className="flex justify-between">
                      <span className="text-fg-muted">Прогноз на конец периода</span>
                      <span className="font-semibold tabular-nums">
                        {isMoney(primaryRow.metric) ? formatCurrency(projectedTotal) : formatNumber(Math.round(projectedTotal))}
                      </span>
                    </div>
                    {planVal > 0 && (
                      <div className="flex justify-between">
                        <span className="text-fg-muted">% от плана</span>
                        <span className={cn(
                          'font-semibold tabular-nums',
                          projectedTotal >= planVal ? 'text-emerald-700' : 'text-amber-600',
                        )}>
                          {((projectedTotal / planVal) * 100).toFixed(1)}%
                        </span>
                      </div>
                    )}
                    {neededPace != null && (
                      <div className="flex justify-between border-t border-border-subtle pt-1.5 mt-1.5">
                        <span className="text-fg-muted">
                          Нужно {isMoney(primaryRow.metric) ? '₽/день' : 'шт/день'} для плана
                        </span>
                        <span className="font-semibold tabular-nums text-blue-600">
                          {isMoney(primaryRow.metric) ? formatCurrency(neededPace) : formatNumber(neededPace)}
                        </span>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <p className="text-sm text-fg-muted text-center py-8">Нет данных</p>
              )}
            </Card>

            {/* БЛОК 3 — Прогресс и серия */}
            <Card className="p-5 flex flex-col gap-4">
              <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">
                Прогресс месяца
              </p>
              {primaryRow ? (
                <>
                  <div className="flex flex-col gap-1.5">
                    <div className="flex justify-between text-sm">
                      <span className="text-fg-muted">
                        Факт: {isMoney(primaryRow.metric) ? formatCurrency(factVal) : formatNumber(Math.round(factVal))}
                      </span>
                      <span className="text-fg-muted">
                        План: {planVal > 0 ? (isMoney(primaryRow.metric) ? formatCurrency(planVal) : formatNumber(Math.round(planVal))) : '—'}
                      </span>
                    </div>
                    <div className="w-full h-4 bg-bg-subtle rounded-full overflow-hidden">
                      <div
                        className={cn(
                          'h-full rounded-full transition-all',
                          progressPct >= 100 ? 'bg-emerald-500' :
                          progressPct >= 80  ? 'bg-amber-400' : 'bg-rose-400',
                        )}
                        style={{ width: `${progressPct}%` }}
                      />
                    </div>
                    <div className="text-xs text-fg-muted text-right">
                      {progressPct.toFixed(1)}% выполнено
                    </div>
                  </div>

                  <div className="flex items-center justify-between text-sm border-t border-border-subtle pt-3">
                    <span className="text-fg-muted">
                      День {daysPassed} из {totalDays}
                    </span>
                    <span className="text-fg-muted">
                      Осталось {remainingDays} дн.
                    </span>
                  </div>

                  {dailyFact && (
                    <div className={cn(
                      'flex items-center gap-3 rounded-md px-4 py-3',
                      dailyFact.streak > 0 ? 'bg-emerald-50 border border-emerald-200' : 'bg-bg-subtle',
                    )}>
                      <span className="text-2xl">
                        {dailyFact.streak > 0 ? '🔥' : '❄️'}
                      </span>
                      <div>
                        <p className="text-sm font-medium text-fg">
                          Серия: {dailyFact.streak} {dailyFact.streak === 1 ? 'день' : dailyFact.streak < 5 ? 'дня' : 'дней'} в зелёной зоне
                        </p>
                        <p className="text-xs text-fg-muted">
                          Дней в зелёной: {dailyFact.days.filter((d) => d.green).length} из {dailyFact.days.length}
                        </p>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <p className="text-sm text-fg-muted text-center py-8">Нет данных</p>
              )}
            </Card>

            {/* БЛОК 4 — Рейтинг KPI */}
            <Card className="p-5 flex flex-col gap-4">
              <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">
                Рейтинг команды
              </p>
              {ratingData.length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-8 text-fg-muted">
                  <p className="text-sm">KPI не назначены</p>
                  <Button size="sm" variant="ghost" onClick={() => setTab('kpi')}>
                    Назначить KPI →
                  </Button>
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  {ratingData.map((k, i) => {
                    const barColor =
                      (k.pct ?? 0) >= 100 ? '#10b981' :
                      (k.pct ?? 0) >= 80  ? '#f59e0b' : '#ef4444'
                    const barPct = Math.min(k.pct ?? 0, 150)
                    const name = k.manager_name ?? KPI_METRIC_LABEL[k.metric_code] ?? k.metric_code
                    return (
                      <div key={k.id} className="flex items-center gap-3">
                        <span className="text-xs font-bold text-fg-muted w-5 text-right shrink-0">
                          {i + 1}.
                        </span>
                        <span className="text-sm text-fg min-w-0 truncate w-28">{name}</span>
                        <div className="flex-1 h-5 bg-bg-subtle rounded overflow-hidden relative">
                          <div
                            className="h-full rounded transition-all"
                            style={{ width: `${(barPct / 150) * 100}%`, background: barColor }}
                          />
                          {k.pct != null && (
                            <span className="absolute right-2 top-0 h-full flex items-center text-[10px] font-medium text-fg">
                              {k.pct.toFixed(1)}%
                            </span>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </Card>

          </div>
        )
      })()}
    </div>
  )
}
