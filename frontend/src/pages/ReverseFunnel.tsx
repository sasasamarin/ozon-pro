import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Target, Sparkles, Loader2, TrendingUp, Megaphone, TrendingDown } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'

type TargetMetric = 'revenue' | 'orders' | 'net_profit' | 'delivered'

interface ScenarioOutput {
  name: string
  impressions: number
  orders: number
  delivered: number
  seller_price: number
  revenue: number
  ad_spend: number
  net_profit: number
  drivers_explanation: string[]
}

interface ReverseScenario {
  lever: 'impressions' | 'ad_spend' | 'seller_price'
  label: string
  feasible: boolean
  reason: string | null
  lever_value_pct: number | null
  achieved: ScenarioOutput | null
}

interface ReverseFunnelResponse {
  product_name: string
  offer_id: string
  target_metric: TargetMetric
  target_value: number
  days_analyzed: number
  base: {
    revenue: number
    orders: number
    delivered: number
    net_profit: number
    ad_spend: number
    seller_price: number
    impressions: number
  }
  scenarios: ReverseScenario[]
}

interface ProductOption {
  id: string
  name: string
  offer_id: string
}

const METRIC_LABEL: Record<TargetMetric, string> = {
  revenue: 'Выручка ₽',
  orders: 'Заказы (шт)',
  net_profit: 'Чистая прибыль ₽',
  delivered: 'Доставлено (шт)',
}

const LEVER_ICON: Record<string, JSX.Element> = {
  impressions: <TrendingUp className="w-4 h-4 text-indigo-600" />,
  ad_spend: <Megaphone className="w-4 h-4 text-amber-600" />,
  seller_price: <TrendingDown className="w-4 h-4 text-rose-600" />,
}

export function ReverseFunnel() {
  const [productId, setProductId] = useState<string>('')
  const [targetMetric, setTargetMetric] = useState<TargetMetric>('revenue')
  const [targetValue, setTargetValue] = useState('5000000')
  const [days, setDays] = useState(60)

  const { data: products } = useQuery<ProductOption[]>({
    queryKey: ['products-list-simple'],
    queryFn: async () => {
      const r = await api.get('/products/?limit=200&is_archived=false')
      const list = Array.isArray(r.data) ? r.data : (r.data.items ?? [])
      return list.map((p: { id: string; name: string; offer_id: string }) => ({
        id: p.id, name: p.name, offer_id: p.offer_id,
      }))
    },
  })

  const solve = useMutation<ReverseFunnelResponse>({
    mutationFn: async () => {
      const r = await api.post('/analytics/reverse-funnel/solve', {
        product_id: productId,
        target_metric: targetMetric,
        target_value: parseFloat(targetValue),
        days,
      })
      return r.data
    },
  })

  const result = solve.data
  const fmt = (v: number) =>
    targetMetric === 'revenue' || targetMetric === 'net_profit'
      ? formatCurrency(v)
      : formatNumber(v)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <div className="inline-flex items-center gap-2 rounded-full border border-border-subtle bg-bg-subtle/60 px-2.5 py-1 text-xs font-medium text-fg-muted">
          <Sparkles className="w-3 h-3" />
          Killer-feature
        </div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight mt-3">Обратная воронка</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          Задай цель → расчёт через β-эластичности (трафик / реклама / цена) на твоих данных.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* === Форма === */}
        <Card className="p-5 lg:col-span-1">
          <h3 className="text-base font-semibold text-fg mb-4 flex items-center gap-2">
            <Target className="w-4 h-4 text-fg-muted" />
            Цель
          </h3>
          <div className="flex flex-col gap-3">
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Товар</label>
              <select
                value={productId}
                onChange={(e) => setProductId(e.target.value)}
                className="w-full px-3 py-2 border border-fg-subtle/30 rounded-lg text-sm bg-bg"
              >
                <option value="">— выбери товар —</option>
                {products?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.offer_id} — {p.name.slice(0, 50)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Метрика цели</label>
              <select
                value={targetMetric}
                onChange={(e) => setTargetMetric(e.target.value as TargetMetric)}
                className="w-full px-3 py-2 border border-fg-subtle/30 rounded-lg text-sm bg-bg"
              >
                {(Object.entries(METRIC_LABEL) as [TargetMetric, string][]).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">
                Значение цели
              </label>
              <Input value={targetValue} onChange={(e) => setTargetValue(e.target.value)} type="number" />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">
                Окно для β-расчёта
              </label>
              <div className="flex gap-1.5">
                {[28, 60, 90, 180].map((d) => (
                  <button key={d} onClick={() => setDays(d)} className={cn(
                    'px-2 py-1 rounded text-xs border',
                    days === d ? 'border-fg bg-fg text-bg'
                               : 'border-border-subtle text-fg-muted hover:bg-bg-subtle',
                  )}>{d}д</button>
                ))}
              </div>
            </div>
            <Button
              onClick={() => solve.mutate()}
              disabled={!productId || !targetValue || solve.isPending}
              className="mt-2"
            >
              {solve.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Посчитать'}
            </Button>
          </div>
        </Card>

        {/* === Результат === */}
        <Card className="p-5 lg:col-span-2">
          <h3 className="text-base font-semibold text-fg mb-4">3 сценария достижения</h3>

          {!result ? (
            <p className="text-sm text-fg-muted">
              Выбери товар и метрику цели → нажми «Посчитать». Алгоритм найдёт нужное значение
              рычага (трафик / бюджет / цена) через bisection по β-эластичностям.
            </p>
          ) : (
            <>
              <div className="mb-4 grid grid-cols-2 gap-3 text-sm">
                <div className="px-3 py-2 bg-bg-subtle/30 rounded">
                  <div className="text-[10px] uppercase text-fg-muted">Сейчас за {result.days_analyzed}д</div>
                  <div className="font-medium tabular-nums">
                    {fmt(
                      targetMetric === 'revenue' ? result.base.revenue
                        : targetMetric === 'orders' ? result.base.orders
                        : targetMetric === 'net_profit' ? result.base.net_profit
                        : result.base.delivered
                    )}
                  </div>
                </div>
                <div className="px-3 py-2 bg-indigo-50 border border-indigo-200 rounded">
                  <div className="text-[10px] uppercase text-indigo-700">Цель</div>
                  <div className="font-medium tabular-nums text-indigo-900">
                    {fmt(result.target_value)}
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                {result.scenarios.map((sc) => (
                  <ScenarioCard key={sc.lever} sc={sc} fmt={fmt} metric={targetMetric} />
                ))}
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  )
}

function ScenarioCard({
  sc, fmt, metric,
}: {
  sc: ReverseScenario
  fmt: (v: number) => string
  metric: TargetMetric
}) {
  const a = sc.achieved
  const actualValue = a ? (
    metric === 'revenue' ? a.revenue
    : metric === 'orders' ? a.orders
    : metric === 'net_profit' ? a.net_profit
    : a.delivered
  ) : null

  const leverText = sc.lever_value_pct != null && (
    sc.lever === 'impressions' ? `${sc.lever_value_pct > 0 ? '+' : ''}${sc.lever_value_pct}% трафика`
    : sc.lever === 'ad_spend' ? `${sc.lever_value_pct > 0 ? '+' : ''}${sc.lever_value_pct}% бюджет рекламы`
    : `${sc.lever_value_pct > 0 ? '+' : ''}${sc.lever_value_pct}% к цене`
  )

  return (
    <div className={cn(
      'border rounded-md px-4 py-3',
      sc.feasible
        ? 'border-emerald-200 bg-emerald-50/30'
        : 'border-amber-200 bg-amber-50/30',
    )}>
      <div className="flex items-start gap-3">
        <div className="mt-0.5">{LEVER_ICON[sc.lever]}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <div className="font-medium text-fg">{sc.label}</div>
            {sc.feasible ? (
              <div className="text-sm font-semibold tabular-nums text-emerald-700">{leverText}</div>
            ) : (
              <div className="text-xs text-amber-700">недостижимо</div>
            )}
          </div>
          {a && (
            <div className="mt-2 grid grid-cols-4 gap-2 text-xs">
              <Stat label="Показы" v={formatNumber(a.impressions)} />
              <Stat label="Заказы" v={formatNumber(a.orders)} />
              <Stat label="Реклама" v={formatCurrency(a.ad_spend)} />
              <Stat label="Прибыль" v={formatCurrency(a.net_profit)} accent />
            </div>
          )}
          {actualValue != null && (
            <div className="mt-2 text-xs text-fg-muted">
              Достигнутое значение метрики: <b className="text-fg">{fmt(actualValue)}</b>
            </div>
          )}
          {sc.reason && (
            <div className="mt-2 text-xs text-amber-800">⚠ {sc.reason}</div>
          )}
          {a?.drivers_explanation && a.drivers_explanation.length > 0 && (
            <ul className="mt-2 text-[11px] text-fg-muted list-disc list-inside space-y-0.5">
              {a.drivers_explanation.map((d, i) => <li key={i}>{d}</li>)}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

function Stat({ label, v, accent }: { label: string; v: string; accent?: boolean }) {
  return (
    <div>
      <div className="text-[10px] text-fg-muted">{label}</div>
      <div className={cn('font-medium tabular-nums', accent && 'text-emerald-700')}>{v}</div>
    </div>
  )
}
