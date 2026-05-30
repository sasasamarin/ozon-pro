/**
 * /analytics/plan-purchase — обратный расчёт «цель → закупка → факт».
 *
 * 5 шагов:
 *   1) Цель: продать X шт ИЛИ получить Y ₽ прибыли
 *   2) Backend считает обратно — что нужно
 *   3) 3 сценария: текущие / цена+10% / реклама+50%
 *   4) План закупки (батчи помесячно)
 *   5) (TODO) Факт vs план — отдельный progress endpoint
 */
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Target, Loader2, TrendingUp, AlertTriangle, CheckCircle2, ShoppingCart } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'

interface PlanInput {
  goal_type: 'units' | 'profit' | 'revenue'
  goal_value: number
  period_days: number
  product_id?: string
  lead_time_days: number
  safety_stock_days: number
  baseline_window_days: number
}

interface Scenario {
  name: string
  description: string
  units_needed: number
  revenue: number
  gross_profit: number
  avg_price: number
  margin_pct: number
  velocity_required: number
  velocity_today: number
  velocity_gap_pct: number
  reachable: boolean
  advice: string
}

interface PurchaseBatch {
  month_index: number
  month_label: string
  units_to_order: number
  reasoning: string
}

interface PurchasePlanResp {
  period_from: string
  period_to: string
  product_id: string | null
  product_name: string | null
  baseline: {
    window_days: number
    units_sold: number
    revenue: number
    avg_price: number
    velocity: number
    ad_spend: number
    drr_pct: number
    margin_pct: number
    cost_price: number
    has_cost_price: boolean
  }
  scenarios: Scenario[]
  purchase_plan: {
    total_units: number
    avg_batch_units: number
    batches: PurchaseBatch[]
    reorder_point_units: number
  }
  note: string
}

interface ProductLite {
  id: string
  name: string
  offer_id: string
  is_archived: boolean
}

export function PlanPurchase() {
  const [goalType, setGoalType] = useState<'units' | 'profit' | 'revenue'>('units')
  const [goalValue, setGoalValue] = useState('3000')
  const [periodDays, setPeriodDays] = useState('90')
  const [productId, setProductId] = useState('')
  const [leadTime, setLeadTime] = useState('14')
  const [safety, setSafety] = useState('7')

  const { data: products } = useQuery<ProductLite[]>({
    queryKey: ['products', 'lite-plan'],
    queryFn: async () => (await api.get('/products/')).data,
  })

  const calc = useMutation<PurchasePlanResp, Error, PlanInput>({
    mutationFn: async (payload) =>
      (await api.post('/analytics/plan-purchase/calculate', payload)).data,
  })

  const onSubmit = () => {
    calc.mutate({
      goal_type: goalType,
      goal_value: parseFloat(goalValue) || 0,
      period_days: parseInt(periodDays) || 90,
      product_id: productId || undefined,
      lead_time_days: parseInt(leadTime) || 14,
      safety_stock_days: parseInt(safety) || 7,
      baseline_window_days: 28,
    })
  }

  const result = calc.data
  const goalUnit = goalType === 'units' ? 'шт' : '₽'
  const goalLabel =
    goalType === 'units' ? 'продать ШТУК' :
    goalType === 'profit' ? 'получить прибыль (₽)' :
    'выручка (₽)'

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight flex items-center gap-2">
          <Target className="w-7 h-7 text-indigo-600" />
          План → Закупка
        </h1>
        <p className="text-sm text-fg-muted mt-1.5">
          Скажи чего хочешь — система покажет сценарии и распишет закупку.
        </p>
      </div>

      {/* ШАГ 1: Цель */}
      <Card className="p-5">
        <h2 className="text-base font-semibold text-fg mb-3">Шаг 1: Цель</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <label className="block text-[11px] text-fg-muted uppercase mb-1">Что хочешь</label>
            <select value={goalType} onChange={(e) => setGoalType(e.target.value as any)}
              className="h-9 px-3 rounded-md border border-border bg-surface text-sm w-full">
              <option value="units">Продать штук</option>
              <option value="profit">Получить прибыль (₽)</option>
              <option value="revenue">Получить выручку (₽)</option>
            </select>
          </div>
          <div>
            <label className="block text-[11px] text-fg-muted uppercase mb-1">{goalLabel}</label>
            <Input value={goalValue} onChange={(e) => setGoalValue(e.target.value)}
                   type="number" placeholder="3000" />
          </div>
          <div>
            <label className="block text-[11px] text-fg-muted uppercase mb-1">За сколько дней</label>
            <Input value={periodDays} onChange={(e) => setPeriodDays(e.target.value)}
                   type="number" placeholder="90" />
          </div>
          <div>
            <label className="block text-[11px] text-fg-muted uppercase mb-1">Товар (опционально)</label>
            <select value={productId} onChange={(e) => setProductId(e.target.value)}
              className="h-9 px-3 rounded-md border border-border bg-surface text-sm w-full">
              <option value="">— все товары —</option>
              {products?.filter((p) => !p.is_archived).map((p) => (
                <option key={p.id} value={p.id}>{p.name.slice(0, 60)}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
          <div>
            <label className="block text-[11px] text-fg-muted uppercase mb-1">Lead time (дн)</label>
            <Input value={leadTime} onChange={(e) => setLeadTime(e.target.value)} type="number" />
          </div>
          <div>
            <label className="block text-[11px] text-fg-muted uppercase mb-1">Safety stock (дн)</label>
            <Input value={safety} onChange={(e) => setSafety(e.target.value)} type="number" />
          </div>
          <div className="col-span-2 md:col-span-2 flex items-end">
            <Button onClick={onSubmit} disabled={calc.isPending} className="w-full">
              {calc.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Посчитать'}
            </Button>
          </div>
        </div>

        {calc.isError && (
          <div className="mt-3 text-sm text-rose-700 bg-rose-50 px-3 py-2 rounded">
            {calc.error?.message || 'Ошибка'}
          </div>
        )}
      </Card>

      {/* ШАГ 2: Baseline */}
      {result && (
        <>
          <Card className="p-5">
            <h2 className="text-base font-semibold text-fg mb-3">
              Шаг 2: Что у нас сейчас (за {result.baseline.window_days} дней)
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
              <Stat label="Продано" value={`${formatNumber(result.baseline.units_sold)} шт`} />
              <Stat label="Выручка" value={formatCurrency(result.baseline.revenue)} />
              <Stat label="Скорость" value={`${result.baseline.velocity.toFixed(1)} шт/д`} />
              <Stat label="Средний чек" value={formatCurrency(result.baseline.avg_price)} />
              <Stat label="ДРР" value={`${result.baseline.drr_pct.toFixed(1)}%`} />
              <Stat label="Маржа" value={
                result.baseline.has_cost_price
                  ? `${result.baseline.margin_pct.toFixed(1)}%`
                  : `~${result.baseline.margin_pct.toFixed(0)}% (нет себестоимости)`
              } />
            </div>
            {!result.baseline.has_cost_price && (
              <p className="text-xs text-amber-700 mt-2 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5" />
                Себестоимость не задана — расчёт по дефолтной марже 30%. Зайди в товар → "Себестоимость" для точности.
              </p>
            )}
          </Card>

          {/* ШАГ 3: Сценарии */}
          <div>
            <h2 className="text-base font-semibold text-fg mb-3 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-indigo-600" />
              Шаг 3: 3 сценария достижения цели
              <span className="text-fg-muted font-normal">
                ({goalValue} {goalUnit} за {periodDays} дн)
              </span>
            </h2>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {result.scenarios.map((s, i) => (
                <Card key={i} className={cn(
                  'p-5 border-2',
                  s.reachable ? 'border-emerald-300' : 'border-amber-300',
                )}>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-bold text-fg">{s.name}</h3>
                    {s.reachable ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-700" />
                    ) : (
                      <AlertTriangle className="w-4 h-4 text-amber-700" />
                    )}
                  </div>
                  <p className="text-xs text-fg-muted mb-3">{s.description}</p>

                  <div className="space-y-1.5 text-sm">
                    <div className="flex justify-between">
                      <span className="text-fg-muted">Штук нужно:</span>
                      <strong className="tabular-nums">{formatNumber(s.units_needed)}</strong>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-fg-muted">Выручка:</span>
                      <strong className="tabular-nums">{formatCurrency(s.revenue)}</strong>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-fg-muted">Прибыль:</span>
                      <strong className="tabular-nums text-emerald-700">{formatCurrency(s.gross_profit)}</strong>
                    </div>
                    <div className="flex justify-between pt-2 border-t border-border-subtle">
                      <span className="text-fg-muted">Темп нужен:</span>
                      <strong className="tabular-nums">{s.velocity_required.toFixed(1)} шт/д</strong>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-fg-muted">Сейчас:</span>
                      <span className="tabular-nums text-fg-muted">{s.velocity_today.toFixed(1)} шт/д</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-fg-muted">Разрыв:</span>
                      <span className={cn('tabular-nums font-semibold',
                        s.velocity_gap_pct <= 15 ? 'text-emerald-700' :
                        s.velocity_gap_pct <= 50 ? 'text-amber-700' : 'text-rose-700')}>
                        {s.velocity_gap_pct > 0 ? '+' : ''}{s.velocity_gap_pct.toFixed(0)}%
                      </span>
                    </div>
                  </div>

                  <div className={cn(
                    'mt-3 text-xs p-2 rounded',
                    s.reachable ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-800',
                  )}>
                    {s.advice}
                  </div>
                </Card>
              ))}
            </div>
          </div>

          {/* ШАГ 4: План закупки */}
          <Card className="p-5">
            <h2 className="text-base font-semibold text-fg mb-3 flex items-center gap-2">
              <ShoppingCart className="w-4 h-4 text-indigo-600" />
              Шаг 4: План закупки
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <Stat label="Всего нужно" value={`${formatNumber(result.purchase_plan.total_units)} шт`} />
              <Stat label="В месяц (средн.)" value={`${formatNumber(result.purchase_plan.avg_batch_units)} шт`} />
              <Stat label="Точка перезаказа" value={`${formatNumber(result.purchase_plan.reorder_point_units)} шт`} />
              <Stat label="Партий" value={`${result.purchase_plan.batches.length}`} />
            </div>

            <table className="w-full text-sm">
              <thead className="bg-bg-subtle/40 border-y border-border-subtle">
                <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                  <th className="py-2 px-3 font-medium">Месяц</th>
                  <th className="py-2 px-3 font-medium text-right">К закупке</th>
                  <th className="py-2 px-3 font-medium">Обоснование</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {result.purchase_plan.batches.map((b) => (
                  <tr key={b.month_index} className="hover:bg-bg-subtle/30">
                    <td className="py-2 px-3 capitalize">{b.month_label}</td>
                    <td className="py-2 px-3 text-right tabular-nums font-semibold">
                      {formatNumber(b.units_to_order)} шт
                    </td>
                    <td className="py-2 px-3 text-xs text-fg-muted">{b.reasoning}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          {/* note */}
          <Card className="p-3 bg-bg-subtle/40 border border-border-subtle">
            <p className="text-xs text-fg-muted">{result.note}</p>
          </Card>
        </>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border-subtle bg-bg-subtle/30 px-3 py-2">
      <div className="text-[10px] font-medium text-fg-muted uppercase tracking-wider">{label}</div>
      <div className="text-sm font-semibold text-fg mt-0.5 tabular-nums">{value}</div>
    </div>
  )
}
