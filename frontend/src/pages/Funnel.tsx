import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Eye, ShoppingCart, ShoppingBag, CheckCircle2,
  ArrowUpRight, ArrowDownRight, Filter, Loader2,
  Image as ImageIcon, Search, Calendar,
  TrendingUp, TrendingDown,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'

interface FunnelKPI {
  impressions: number
  to_cart: number
  orders: number
  delivered: number
  revenue: number
  cart_conv_pct: number | null
  order_conv_pct: number | null
  delivery_conv_pct: number | null
  overall_conv_pct: number | null
}

interface FunnelV2Resp {
  period_from: string
  period_to: string
  product_id: string | null
  product_name: string | null
  has_data: boolean
  kpi: FunnelKPI
  prev_kpi: FunnelKPI | null
}

interface FunnelDaily {
  date: string
  impressions: number
  to_cart: number
  orders: number
  delivered: number
  overall_conv_pct: number | null
}

interface BestWorstDay {
  date: string
  impressions: number
  delivered: number
  overall_conv_pct: number
  revenue: number
}

interface ProductLite {
  id: string
  name: string
  offer_id: string
  image_url: string | null
}

const STEP_ICONS = [Eye, ShoppingCart, ShoppingBag, CheckCircle2]

const PRESETS = [
  { key: '7', label: '7 дней' },
  { key: '30', label: '30 дней' },
  { key: '90', label: '90 дней' },
  { key: '365', label: 'Год' },
  { key: '514', label: '17 мес' },
]

type DrillType = 'impressions' | 'to_cart' | 'orders' | 'delivered' | null

export function Funnel() {
  const { selectedCabinetIds } = useCabinetStore()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()

  const days = parseInt(params.get('days') || '30', 10)
  const productId = params.get('p') || ''
  const compare = (params.get('cmp') || 'prev_period') as 'none' | 'prev_period' | 'year_ago'
  const [productSearch, setProductSearch] = useState('')
  const [drillStep, setDrillStep] = useState<DrillType>(null)

  const updateParam = (k: string, v: string | undefined) => {
    const p = new URLSearchParams(params)
    if (v) p.set(k, v); else p.delete(k)
    setParams(p, { replace: true })
  }

  // Список продуктов (для селектора)
  const { data: products } = useQuery<ProductLite[]>({
    queryKey: ['products', 'lite'],
    queryFn: async () => {
      const all = (await api.get('/products/')).data as Array<{ id: string; name: string; offer_id: string; image_url: string | null }>
      return all.map((p) => ({ id: p.id, name: p.name, offer_id: p.offer_id, image_url: p.image_url }))
    },
  })

  const selectedProduct = useMemo(
    () => (products || []).find((p) => p.id === productId),
    [products, productId],
  )

  const filteredProducts = useMemo(() => {
    if (!products) return []
    const s = productSearch.trim().toLowerCase()
    if (!s) return products.slice(0, 20)
    return products
      .filter((p) => p.name.toLowerCase().includes(s) || p.offer_id.toLowerCase().includes(s))
      .slice(0, 20)
  }, [products, productSearch])

  const { data, isLoading } = useQuery<FunnelV2Resp>({
    queryKey: ['funnel-v2', selectedCabinetIds, days, productId, compare],
    queryFn: async () => {
      const p = new URLSearchParams({ days: String(days), compare })
      if (productId) p.append('product_id', productId)
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      return (await api.get(`/analytics/funnel/v2/?${p.toString()}`)).data
    },
  })

  const { data: daily } = useQuery<FunnelDaily[]>({
    queryKey: ['funnel-v2', 'daily', selectedCabinetIds, days, productId],
    queryFn: async () => {
      const p = new URLSearchParams({ days: String(days) })
      if (productId) p.append('product_id', productId)
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      return (await api.get(`/analytics/funnel/v2/daily?${p.toString()}`)).data
    },
    enabled: drillStep !== null,
  })

  const { data: bestWorst } = useQuery<{ best: BestWorstDay[]; worst: BestWorstDay[] }>({
    queryKey: ['funnel-v2', 'bw', selectedCabinetIds, days, productId],
    queryFn: async () => {
      const p = new URLSearchParams({ days: String(days) })
      if (productId) p.append('product_id', productId)
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      return (await api.get(`/analytics/funnel/v2/best-worst-days?${p.toString()}`)).data
    },
  })

  const kpi = data?.kpi
  const prev = data?.prev_kpi
  const maxValue = useMemo(() => {
    if (!kpi) return 1
    return Math.max(1, kpi.impressions, kpi.to_cart, kpi.orders, kpi.delivered)
  }, [kpi])

  const steps = useMemo(() => {
    if (!kpi) return []
    return [
      { key: 'impressions' as const, label: 'Показы', value: kpi.impressions, conv: null },
      { key: 'to_cart' as const, label: 'В корзину', value: kpi.to_cart, conv: kpi.cart_conv_pct },
      { key: 'orders' as const, label: 'Заказы', value: kpi.orders, conv: kpi.order_conv_pct },
      { key: 'delivered' as const, label: 'Доставлено', value: kpi.delivered, conv: kpi.delivery_conv_pct },
    ]
  }, [kpi])

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Воронка</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          {data?.product_name ? <>SKU: <strong>{data.product_name}</strong></> : 'По всему кабинету'} · {data?.period_from} … {data?.period_to}
        </p>
      </div>

      {/* === TOOLBAR === */}
      <Card className="p-3 flex flex-wrap items-center gap-2">
        {PRESETS.map((p) => (
          <button key={p.key} onClick={() => updateParam('days', p.key)} className={cn(
            'px-3 py-1.5 rounded-md text-xs border transition-colors',
            String(days) === p.key ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
          )}>
            {p.label}
          </button>
        ))}
        <div className="w-px h-5 bg-border-subtle mx-2" />
        <span className="text-xs text-fg-muted">Сравнение:</span>
        {([
          ['none', 'нет'],
          ['prev_period', 'vs прошлый'],
          ['year_ago', 'vs год назад'],
        ] as const).map(([k, l]) => (
          <button key={k} onClick={() => updateParam('cmp', k)} className={cn(
            'px-2 py-1 rounded text-xs border',
            compare === k ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle',
          )}>
            {l}
          </button>
        ))}
      </Card>

      {/* === PRODUCT SELECTOR === */}
      <Card className="p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-fg">Выберите товар</h3>
          {productId && (
            <button onClick={() => updateParam('p', undefined)} className="text-xs text-fg-muted hover:text-fg">
              × сбросить (показать общую)
            </button>
          )}
        </div>
        <div className="relative mb-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-fg-subtle" />
          <Input value={productSearch} onChange={(e) => setProductSearch(e.target.value)}
            placeholder="название или offer_id" className="pl-9" />
        </div>
        <div className="flex flex-wrap gap-2 max-h-[180px] overflow-y-auto">
          {filteredProducts.map((p) => (
            <button key={p.id} onClick={() => updateParam('p', p.id)} className={cn(
              'flex items-center gap-2 px-2 py-1.5 rounded-md border text-xs',
              productId === p.id ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
            )}>
              {p.image_url ? (
                <img src={p.image_url} alt="" className="w-5 h-5 rounded object-cover shrink-0" />
              ) : (
                <ImageIcon className="w-4 h-4 shrink-0" />
              )}
              <span className="truncate max-w-[180px]">{p.offer_id}</span>
            </button>
          ))}
        </div>
      </Card>

      {/* === KPI ROW === */}
      {isLoading ? (
        <Card className="py-16 flex justify-center"><Loader2 className="w-5 h-5 animate-spin" /></Card>
      ) : !data?.has_data ? (
        <Card className="py-12 flex flex-col items-center text-fg-muted text-sm">
          <Filter className="w-8 h-8 mb-2 text-fg-subtle" />
          <p>Нет данных за период</p>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <ConvCard label="Сквозная" curr={kpi!.overall_conv_pct} prev={prev?.overall_conv_pct} />
            <ConvCard label="В корзину" curr={kpi!.cart_conv_pct} prev={prev?.cart_conv_pct} />
            <ConvCard label="Корзина → заказ" curr={kpi!.order_conv_pct} prev={prev?.order_conv_pct} />
            <ConvCard label="Заказ → выкуп" curr={kpi!.delivery_conv_pct} prev={prev?.delivery_conv_pct} />
          </div>

          {/* === STEPS === */}
          <Card className="p-5">
            <div className="flex justify-between mb-4">
              <h2 className="text-base font-semibold text-fg">Шаги воронки</h2>
              <p className="text-xs text-fg-muted">кликни на шаг → детализация по дням</p>
            </div>
            <div className="flex flex-col gap-3">
              {steps.map((step, idx) => {
                const Icon = STEP_ICONS[idx]
                const width = Math.max(2, (step.value / maxValue) * 100)
                const colors = ['bg-indigo-400', 'bg-violet-400', 'bg-emerald-400', 'bg-amber-400']
                const isActive = drillStep === step.key
                return (
                  <button key={step.key} onClick={() => setDrillStep(isActive ? null : step.key)}
                    className={cn(
                      'flex items-center gap-3 group',
                      isActive && 'ring-2 ring-fg/20 rounded-lg p-2 -m-2',
                    )}
                  >
                    <div className="w-9 h-9 rounded-lg border bg-bg-subtle/30 flex items-center justify-center shrink-0">
                      <Icon className="w-4 h-4 text-fg-muted" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex justify-between items-baseline mb-1">
                        <span className="text-sm font-medium text-fg">{step.label}</span>
                        <span className="text-lg font-semibold text-fg tabular-nums">{formatNumber(step.value)}</span>
                      </div>
                      <div className="relative h-3 rounded-full bg-bg-subtle overflow-hidden">
                        <div className={cn('h-full rounded-full transition-all', colors[idx])} style={{ width: `${width}%` }} />
                      </div>
                      {step.conv != null && idx > 0 && (
                        <div className="text-[11px] text-fg-muted mt-1 text-left">
                          от предыдущего: <strong className="text-fg">{step.conv}%</strong>
                        </div>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
          </Card>

          {/* === DRILL-DOWN === */}
          {drillStep && (daily?.length ?? 0) > 0 && (
            <Card className="p-5">
              <h3 className="text-base font-semibold text-fg mb-3">
                Drill-down: {drillStep} по дням
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-bg-subtle/50">
                    <tr className="text-left text-xs text-fg-muted uppercase">
                      <th className="py-2 px-3">дата</th>
                      <th className="py-2 px-3 text-right">показы</th>
                      <th className="py-2 px-3 text-right">в корзину</th>
                      <th className="py-2 px-3 text-right">заказы</th>
                      <th className="py-2 px-3 text-right">доставлено</th>
                      <th className="py-2 px-3 text-right">сквозная</th>
                      <th className="py-2 px-3"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-subtle">
                    {daily!.slice().reverse().slice(0, 30).map((d) => (
                      <tr key={d.date} className="hover:bg-bg-subtle/40 cursor-pointer"
                        onClick={() => navigate(`/orders?date_from=${d.date}&date_to=${d.date}`)}
                      >
                        <td className="py-2 px-3 font-mono text-xs">{d.date}</td>
                        <td className="py-2 px-3 text-right tabular-nums">{formatNumber(d.impressions)}</td>
                        <td className="py-2 px-3 text-right tabular-nums">{formatNumber(d.to_cart)}</td>
                        <td className="py-2 px-3 text-right tabular-nums">{formatNumber(d.orders)}</td>
                        <td className="py-2 px-3 text-right tabular-nums">{formatNumber(d.delivered)}</td>
                        <td className="py-2 px-3 text-right tabular-nums font-semibold">
                          {d.overall_conv_pct != null ? `${d.overall_conv_pct}%` : '—'}
                        </td>
                        <td className="py-2 px-3 text-fg-subtle text-xs">→ заказы</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* === BEST/WORST DAYS === */}
          {bestWorst && (bestWorst.best.length > 0 || bestWorst.worst.length > 0) && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card className="p-5">
                <h3 className="text-base font-semibold text-emerald-700 flex items-center gap-2 mb-3">
                  <TrendingUp className="w-4 h-4" /> Лучшие дни по конверсии
                </h3>
                <ul className="text-sm divide-y divide-border-subtle">
                  {bestWorst.best.map((d) => (
                    <li key={d.date} className="py-2 flex justify-between">
                      <span className="font-mono text-xs">{d.date}</span>
                      <span className="text-emerald-700 font-semibold tabular-nums">{d.overall_conv_pct}%</span>
                      <span className="text-fg-muted tabular-nums">{formatNumber(d.impressions)} показов</span>
                    </li>
                  ))}
                </ul>
              </Card>
              <Card className="p-5">
                <h3 className="text-base font-semibold text-rose-700 flex items-center gap-2 mb-3">
                  <TrendingDown className="w-4 h-4" /> Худшие дни по конверсии
                </h3>
                <ul className="text-sm divide-y divide-border-subtle">
                  {bestWorst.worst.map((d) => (
                    <li key={d.date} className="py-2 flex justify-between">
                      <span className="font-mono text-xs">{d.date}</span>
                      <span className="text-rose-700 font-semibold tabular-nums">{d.overall_conv_pct}%</span>
                      <span className="text-fg-muted tabular-nums">{formatNumber(d.impressions)} показов</span>
                    </li>
                  ))}
                </ul>
              </Card>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function ConvCard({ label, curr, prev }: { label: string; curr: number | null; prev?: number | null }) {
  const delta = curr != null && prev != null ? curr - prev : null
  return (
    <Card className="p-4">
      <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">{label}</p>
      <p className="text-[20px] leading-tight font-semibold text-fg mt-1 tabular-nums">
        {curr != null ? `${curr}%` : '—'}
      </p>
      {delta != null && (
        <p className={cn(
          'text-xs mt-1.5 tabular-nums inline-flex items-center gap-0.5',
          delta >= 0 ? 'text-emerald-700' : 'text-rose-700',
        )}>
          {delta >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
          {delta >= 0 ? '+' : ''}{delta.toFixed(2)} п.п.
        </p>
      )}
    </Card>
  )
}
