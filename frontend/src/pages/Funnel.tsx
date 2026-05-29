import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Eye,
  ShoppingCart,
  ShoppingBag,
  CheckCircle2,
  ArrowUpRight,
  ArrowDownRight,
  Filter,
  Image as ImageIcon,
  Loader2,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatNumber, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'

interface FunnelKPI {
  impressions: number
  to_cart: number
  orders: number
  delivered: number
  cart_conv_pct: number | null
  order_conv_pct: number | null
  delivery_conv_pct: number | null
  overall_conv_pct: number | null
}

interface FunnelStep {
  label: string
  value: number
  pct_from_previous: number | null
  pct_from_first: number | null
}

interface FunnelResp {
  period_from: string
  period_to: string
  cabinet_ids: string[]
  has_data: boolean
  kpi: FunnelKPI
  prev_kpi: FunnelKPI | null
  steps: FunnelStep[]
}

interface TopProductFunnel {
  product_id: string
  name: string
  offer_id: string
  image_url: string | null
  impressions: number
  to_cart: number
  orders: number
  delivered: number
  cart_conv_pct: number | null
  order_conv_pct: number | null
  delivery_conv_pct: number | null
  overall_conv_pct: number | null
}

const STEP_ICONS = [Eye, ShoppingCart, ShoppingBag, CheckCircle2]
const STEP_COLORS = [
  'from-indigo-50 to-white text-indigo-600 border-indigo-200',
  'from-violet-50 to-white text-violet-600 border-violet-200',
  'from-emerald-50 to-white text-emerald-600 border-emerald-200',
  'from-amber-50 to-white text-amber-700 border-amber-200',
]
const STEP_BAR_COLORS = [
  'bg-indigo-400',
  'bg-violet-400',
  'bg-emerald-400',
  'bg-amber-400',
]

type SortKey = 'delivered_desc' | 'impressions_desc' | 'overall_conv_desc' | 'overall_conv_asc'

const SORT_LABELS: Record<SortKey, string> = {
  delivered_desc: 'По доставленным',
  impressions_desc: 'По показам',
  overall_conv_desc: 'Лучшая конверсия',
  overall_conv_asc: 'Худшая конверсия',
}

export function Funnel() {
  const { selectedCabinetIds } = useCabinetStore()
  const [days, setDays] = useState(30)
  const [sort, setSort] = useState<SortKey>('delivered_desc')

  const { data, isLoading } = useQuery<FunnelResp>({
    queryKey: ['funnel', selectedCabinetIds, days],
    queryFn: async () => {
      const params = new URLSearchParams({ days: String(days), compare: 'true' })
      selectedCabinetIds.forEach((id) => params.append('cabinet_ids', id))
      const res = await api.get(`/analytics/funnel/?${params.toString()}`)
      return res.data
    },
  })

  const { data: topProducts } = useQuery<TopProductFunnel[]>({
    queryKey: ['funnel', 'products', selectedCabinetIds, days, sort],
    queryFn: async () => {
      const params = new URLSearchParams({
        days: String(days),
        sort,
        limit: '20',
      })
      selectedCabinetIds.forEach((id) => params.append('cabinet_ids', id))
      const res = await api.get(`/analytics/funnel/products?${params.toString()}`)
      return res.data
    },
  })

  const kpi = data?.kpi
  const prev = data?.prev_kpi

  const maxValue = useMemo(() => {
    if (!data?.steps?.length) return 1
    return Math.max(1, ...data.steps.map((s) => s.value))
  }, [data])

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Воронка конверсии</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Показы → корзина → заказ → выкуп · {data?.period_from} … {data?.period_to}
          </p>
        </div>
        <div className="flex gap-2">
          {[7, 30, 90, 365].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={cn(
                'px-3 py-1.5 rounded-md text-sm border transition-colors',
                days === d
                  ? 'border-fg bg-fg text-bg'
                  : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
              )}
            >
              {d === 7 && '7 дней'}
              {d === 30 && '30 дней'}
              {d === 90 && '90 дней'}
              {d === 365 && 'Год'}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <Card className="py-16 flex justify-center items-center text-fg-muted">
          <Loader2 className="w-5 h-5 animate-spin mr-2" /> Загрузка воронки…
        </Card>
      ) : !data?.has_data ? (
        <Card className="py-12 flex flex-col items-center text-fg-muted text-sm">
          <Filter className="w-8 h-8 mb-3 text-fg-subtle" />
          <p>Нет данных за выбранный период по выбранным кабинетам.</p>
        </Card>
      ) : (
        <>
          {/* KPI row */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <KpiTile label="Сквозная конверсия" curr={kpi!.overall_conv_pct} prev={prev?.overall_conv_pct} suffix="%" />
            <KpiTile label="Конверсия в корзину" curr={kpi!.cart_conv_pct} prev={prev?.cart_conv_pct} suffix="%" />
            <KpiTile label="Корзина → заказ" curr={kpi!.order_conv_pct} prev={prev?.order_conv_pct} suffix="%" />
            <KpiTile label="Заказ → выкуп" curr={kpi!.delivery_conv_pct} prev={prev?.delivery_conv_pct} suffix="%" />
          </div>

          {/* Funnel bars */}
          <Card className="p-6">
            <h2 className="text-base font-semibold text-fg">Шаги воронки</h2>
            <p className="text-xs text-fg-muted mt-0.5">
              Каждая полоса — пропорция от предыдущего шага. Под полосой — % от показов.
            </p>
            <div className="mt-6 flex flex-col gap-4">
              {data.steps.map((step, idx) => {
                const Icon = STEP_ICONS[idx]
                const widthPct = Math.max(2, (step.value / maxValue) * 100)
                return (
                  <div key={step.label} className="flex flex-col gap-1.5">
                    <div className="flex items-center gap-3">
                      <div
                        className={cn(
                          'w-9 h-9 rounded-lg bg-gradient-to-br border shadow-sm flex items-center justify-center shrink-0',
                          STEP_COLORS[idx],
                        )}
                      >
                        <Icon className="w-4 h-4" strokeWidth={2} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex justify-between items-baseline mb-1">
                          <span className="text-sm font-medium text-fg">{step.label}</span>
                          <span className="text-lg font-semibold text-fg tabular-nums">
                            {formatNumber(step.value)}
                          </span>
                        </div>
                        <div className="relative h-3 rounded-full bg-bg-subtle overflow-hidden">
                          <div
                            className={cn('h-full rounded-full transition-all', STEP_BAR_COLORS[idx])}
                            style={{ width: `${widthPct}%` }}
                          />
                        </div>
                        <div className="flex justify-between items-center mt-1 text-[11px] text-fg-muted">
                          {step.pct_from_previous != null ? (
                            <span>от предыдущего: <strong className="text-fg">{step.pct_from_previous}%</strong></span>
                          ) : <span />}
                          {step.pct_from_first != null && idx > 0 && (
                            <span>от показов: <strong className="text-fg">{step.pct_from_first}%</strong></span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </Card>

          {/* Top products */}
          <Card className="overflow-hidden">
            <div className="px-6 py-4 border-b border-border-subtle flex items-center justify-between flex-wrap gap-3">
              <div>
                <h2 className="text-base font-semibold text-fg">Топ товаров</h2>
                <p className="text-xs text-fg-muted mt-0.5">за выбранный период · мин. 100 показов</p>
              </div>
              <div className="flex gap-2">
                {(['delivered_desc', 'impressions_desc', 'overall_conv_desc', 'overall_conv_asc'] as SortKey[]).map((k) => (
                  <button
                    key={k}
                    onClick={() => setSort(k)}
                    className={cn(
                      'px-3 py-1.5 rounded-md text-xs border transition-colors',
                      sort === k
                        ? 'border-fg bg-fg text-bg'
                        : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
                    )}
                  >
                    {SORT_LABELS[k]}
                  </button>
                ))}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                  <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                    <th className="py-2.5 px-4 font-medium">товар</th>
                    <th className="py-2.5 px-4 font-medium text-right">показы</th>
                    <th className="py-2.5 px-4 font-medium text-right">в корзину</th>
                    <th className="py-2.5 px-4 font-medium text-right">заказы</th>
                    <th className="py-2.5 px-4 font-medium text-right">доставлено</th>
                    <th className="py-2.5 px-4 font-medium text-right">сквозная</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {(topProducts || []).map((p) => (
                    <tr key={p.product_id} className="hover:bg-bg-subtle/50">
                      <td className="py-2.5 px-4">
                        <div className="flex items-center gap-3 min-w-0">
                          {p.image_url ? (
                            <img src={p.image_url} alt="" className="w-9 h-9 rounded object-cover shrink-0 border border-border-subtle" />
                          ) : (
                            <div className="w-9 h-9 rounded bg-bg-subtle flex items-center justify-center shrink-0">
                              <ImageIcon className="w-4 h-4 text-fg-subtle" />
                            </div>
                          )}
                          <div className="min-w-0">
                            <div className="font-medium text-fg truncate max-w-[280px]">{p.name}</div>
                            <div className="text-xs text-fg-muted font-mono truncate">{p.offer_id}</div>
                          </div>
                        </div>
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums">{formatNumber(p.impressions)}</td>
                      <td className="py-2.5 px-4 text-right tabular-nums">
                        {formatNumber(p.to_cart)}
                        {p.cart_conv_pct != null && (
                          <div className="text-[10px] text-fg-subtle">{p.cart_conv_pct}%</div>
                        )}
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums">
                        {formatNumber(p.orders)}
                        {p.order_conv_pct != null && (
                          <div className="text-[10px] text-fg-subtle">{p.order_conv_pct}%</div>
                        )}
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums">
                        {formatNumber(p.delivered)}
                        {p.delivery_conv_pct != null && (
                          <div className="text-[10px] text-fg-subtle">{p.delivery_conv_pct}%</div>
                        )}
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums font-semibold">
                        {p.overall_conv_pct != null ? `${p.overall_conv_pct}%` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {topProducts && topProducts.length === 0 && (
                <p className="px-6 py-8 text-center text-sm text-fg-muted">
                  Нет товаров с показами ≥ 100 за период.
                </p>
              )}
            </div>
          </Card>
        </>
      )}
    </div>
  )
}

function KpiTile({
  label, curr, prev, suffix,
}: { label: string; curr: number | null; prev: number | null | undefined; suffix?: string }) {
  const delta = curr != null && prev != null ? curr - prev : null
  return (
    <Card className="p-4">
      <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">{label}</p>
      <p className="text-[24px] leading-tight font-semibold text-fg mt-1 tabular-nums">
        {curr != null ? `${curr}${suffix ?? ''}` : '—'}
      </p>
      {delta != null && (
        <p className={cn(
          'text-xs mt-1.5 tabular-nums inline-flex items-center gap-0.5',
          delta >= 0 ? 'text-emerald-700' : 'text-rose-700',
        )}>
          {delta >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
          {delta >= 0 ? '+' : ''}{delta.toFixed(2)} п.п. vs прошлый
        </p>
      )}
    </Card>
  )
}
