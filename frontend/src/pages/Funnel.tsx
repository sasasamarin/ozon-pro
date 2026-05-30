import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Eye, MousePointerClick, ShoppingCart, ShoppingBag, CheckCircle2,
  ArrowUpRight, ArrowDownRight, ArrowDown, Filter, Loader2,
  Image as ImageIcon, Search,
  TrendingUp, TrendingDown, Megaphone, Lock,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { FunnelInsights } from '@/components/FunnelInsights'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'

interface FunnelKPI {
  impressions: number
  clicks: number
  to_cart: number
  orders: number
  delivered: number
  revenue: number
  cart_conv_pct: number | null
  order_conv_pct: number | null
  delivery_conv_pct: number | null
  overall_conv_pct: number | null
  ctr_pct: number | null
  click_to_cart_pct: number | null
}

interface AdBreakdownRow {
  op_type: string
  label: string
  amount: number
  pct_of_total: number
  model: string
}

interface AdBlock {
  total_spend: number
  drr_pct: number | null
  breakdown: AdBreakdownRow[]
  has_data: boolean
}

interface FunnelV2Resp {
  period_from: string
  period_to: string
  product_id: string | null
  product_name: string | null
  has_data: boolean
  kpi: FunnelKPI
  prev_kpi: FunnelKPI | null
  ad: AdBlock
}

interface FunnelDaily {
  date: string
  impressions: number
  impressions_search: number
  impressions_pdp: number
  clicks: number
  to_cart: number
  to_cart_search: number
  to_cart_pdp: number
  orders: number
  delivered: number
  returns: number
  revenue: number
  overall_conv_pct: number | null
  ctr_pct: number | null
  cart_conv_pct: number | null
  order_conv_pct: number | null
  delivery_conv_pct: number | null
}

interface BestWorstDay {
  date: string
  from_value: number
  to_value: number
  conv_pct: number
  revenue: number
}

interface BestWorstResp {
  best: BestWorstDay[]
  worst: BestWorstDay[]
  metric: string
  from_label: string
  to_label: string
}

interface ProductLite {
  id: string
  name: string
  offer_id: string
  image_url: string | null
  total_stock: number
  is_archived: boolean
}

function stockColor(stock: number): string {
  if (stock === 0) return 'bg-rose-500'      // 🔴 стокаут
  if (stock < 10) return 'bg-amber-500'      // 🟡 мало
  return 'bg-emerald-500'                    // 🟢 норма
}

const PRESETS = [
  { key: '7', label: '7 дн' },
  { key: '14', label: '14 дн' },
  { key: '28', label: '28 дн' },
  { key: '30', label: '30 дн' },
  { key: '90', label: '90 дн' },
  { key: '365', label: 'Год' },
  { key: '514', label: '17 мес' },
]

type DrillStep = 'impressions' | 'clicks' | 'to_cart' | 'orders' | 'delivered' | null
type BWMetric = 'overall' | 'cart' | 'order' | 'delivery'

const DRILL_TITLES: Record<Exclude<DrillStep, null>, string> = {
  impressions: 'Детализация: Показы по дням',
  clicks: 'Детализация: Клики по дням',
  to_cart: 'Детализация: В корзину по дням',
  orders: 'Детализация: Заказы по дням',
  delivered: 'Детализация: Доставлено по дням',
}

const BW_LABELS: Record<BWMetric, string> = {
  // Дефолт = order, т.к. заказ происходит в день показа.
  order: 'Показ → Заказ (день в день)',
  cart: 'Показ → Корзина',
  delivery: 'Заказ → Доставка (когорта, может быть лаг)',
  overall: 'Сквозная Показ → Доставка (с лагом доставки — искажает)',
}

const formatDate = (s: string) => new Date(s).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' })

export function Funnel() {
  const { selectedCabinetIds } = useCabinetStore()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()

  const days = parseInt(params.get('days') || '28', 10)
  const productId = params.get('p') || ''
  const compare = (params.get('cmp') || 'prev_period') as 'none' | 'prev_period' | 'year_ago'
  const [productSearch, setProductSearch] = useState('')
  const [drillStep, setDrillStep] = useState<DrillStep>(null)
  // Дефолт = order (Показ→Заказ), а не delivery: доставка может быть через
  // месяц после показа, привязка к дню показа искажает корреляцию.
  const [bwMetric, setBwMetric] = useState<BWMetric>('order')

  const updateParam = (k: string, v: string | undefined) => {
    const p = new URLSearchParams(params)
    if (v) p.set(k, v); else p.delete(k)
    setParams(p, { replace: true })
  }

  const { data: products } = useQuery<ProductLite[]>({
    queryKey: ['products', 'lite'],
    queryFn: async () => {
      const all = (await api.get('/products/')).data as ProductLite[]
      return all
    },
  })

  const filteredProducts = useMemo(() => {
    if (!products) return []
    const s = productSearch.trim().toLowerCase()
    return (s
      ? products.filter((p) => p.name.toLowerCase().includes(s) || p.offer_id.toLowerCase().includes(s))
      : products
    ).slice(0, 20)
  }, [products, productSearch])

  const { data, isLoading, isFetching } = useQuery<FunnelV2Resp>({
    queryKey: ['funnel-v2', selectedCabinetIds, days, productId, compare],
    queryFn: async () => {
      const p = new URLSearchParams({ days: String(days), compare })
      if (productId) p.append('product_id', productId)
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      return (await api.get(`/analytics/funnel/v2/?${p.toString()}`)).data
    },
  })

  const { data: daily, isFetching: dailyLoading } = useQuery<FunnelDaily[]>({
    queryKey: ['funnel-v2', 'daily', selectedCabinetIds, days, productId],
    queryFn: async () => {
      const p = new URLSearchParams({ days: String(days) })
      if (productId) p.append('product_id', productId)
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      return (await api.get(`/analytics/funnel/v2/daily?${p.toString()}`)).data
    },
    enabled: drillStep !== null,
  })

  const { data: bestWorst } = useQuery<BestWorstResp>({
    queryKey: ['funnel-v2', 'bw', selectedCabinetIds, days, productId, bwMetric],
    queryFn: async () => {
      const p = new URLSearchParams({ days: String(days), metric: bwMetric })
      if (productId) p.append('product_id', productId)
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      return (await api.get(`/analytics/funnel/v2/best-worst-days?${p.toString()}`)).data
    },
  })

  const kpi = data?.kpi
  const prev = data?.prev_kpi
  const ad = data?.ad
  const maxValue = useMemo(() => {
    if (!kpi) return 1
    return Math.max(1, kpi.impressions, kpi.clicks, kpi.to_cart, kpi.orders, kpi.delivered)
  }, [kpi])

  const steps = useMemo(() => {
    if (!kpi) return []
    return [
      { key: 'impressions' as const, label: 'Показы',     icon: Eye,                value: kpi.impressions, conv: null,                   convLabel: null,        color: 'bg-indigo-400'  },
      { key: 'clicks'      as const, label: 'Клики',      icon: MousePointerClick,  value: kpi.clicks,      conv: kpi.ctr_pct,            convLabel: 'CTR',       color: 'bg-blue-400'    },
      { key: 'to_cart'     as const, label: 'В корзину',  icon: ShoppingCart,       value: kpi.to_cart,     conv: kpi.click_to_cart_pct,  convLabel: 'в корзину', color: 'bg-violet-400'  },
      { key: 'orders'      as const, label: 'Заказы',     icon: ShoppingBag,        value: kpi.orders,      conv: kpi.order_conv_pct,     convLabel: 'в заказ',   color: 'bg-emerald-400' },
      { key: 'delivered'   as const, label: 'Доставлено', icon: CheckCircle2,       value: kpi.delivered,   conv: kpi.delivery_conv_pct,  convLabel: 'выкуп',     color: 'bg-amber-400'   },
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

      {/* TOOLBAR */}
      <Card className="p-3 flex flex-wrap items-center gap-2">
        {PRESETS.map((p) => {
          const active = String(days) === p.key
          return (
            <button key={p.key} onClick={() => updateParam('days', p.key)}
              disabled={isFetching}
              className={cn(
                'px-3 py-1.5 rounded-md text-xs border transition-colors inline-flex items-center gap-1.5',
                active ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
                isFetching && 'opacity-60 cursor-wait',
              )}>
              {active && isFetching && <Loader2 className="w-3 h-3 animate-spin" />}
              {p.label}
            </button>
          )
        })}
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

      {/* PRODUCT SELECTOR */}
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
            <button
              key={p.id}
              onClick={() => updateParam('p', p.id)}
              title={`${p.name}\nОстаток: ${p.total_stock} шт${p.is_archived ? '\nАРХИВ' : ''}`}
              className={cn(
                'flex items-center gap-2 px-2 py-1.5 rounded-md border text-xs',
                productId === p.id
                  ? 'border-fg bg-fg text-bg'
                  : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
                p.is_archived && 'opacity-60',
              )}
            >
              {p.image_url ? (
                <img src={p.image_url} alt="" className="w-5 h-5 rounded object-cover shrink-0" />
              ) : (
                <ImageIcon className="w-4 h-4 shrink-0" />
              )}
              <span
                className={cn('w-1.5 h-1.5 rounded-full shrink-0', stockColor(p.total_stock))}
                aria-hidden
              />
              <span className="truncate max-w-[160px]">{p.offer_id}</span>
              <span className={cn(
                'tabular-nums shrink-0',
                productId === p.id ? 'text-bg/70' : 'text-fg-subtle',
              )}>{p.total_stock}</span>
              {p.is_archived && (
                <span className="text-[9px] px-1 rounded bg-slate-200 text-slate-600 shrink-0">АРХИВ</span>
              )}
            </button>
          ))}
        </div>
      </Card>

      {isLoading ? (
        <FunnelSkeleton />
      ) : !data?.has_data ? (
        <Card className="py-12 flex flex-col items-center text-fg-muted text-sm">
          <Filter className="w-8 h-8 mb-2 text-fg-subtle" />
          <p>Нет данных за период</p>
        </Card>
      ) : (
        <>
          {/* === 6 KPI === */}
          <div className={cn('grid grid-cols-2 lg:grid-cols-6 gap-3 transition-opacity', isFetching && 'opacity-50')}>
            <ConvCard label="Сквозная" curr={kpi!.overall_conv_pct} prev={prev?.overall_conv_pct} />
            <ConvCard label="CTR (показ→клик)" curr={kpi!.ctr_pct} prev={prev?.ctr_pct} />
            <ConvCard label="В корзину" curr={kpi!.cart_conv_pct} prev={prev?.cart_conv_pct} />
            <ConvCard label="Корзина → заказ" curr={kpi!.order_conv_pct} prev={prev?.order_conv_pct} />
            <ConvCard label="Заказ → выкуп" curr={kpi!.delivery_conv_pct} prev={prev?.delivery_conv_pct} />
            <ConvCard label="ДРР" curr={ad?.drr_pct ?? null} prev={null}
              tooltip={!ad?.has_data ? 'Нет рекламных расходов в transactions за период' : undefined} />
          </div>

          {/* === 5 ШАГОВ ВОРОНКИ + КОНВЕРСИИ КРУПНО + 2 КОЛОНКИ === */}
          <Card className={cn('p-5 transition-opacity', isFetching && 'opacity-50')}>
            <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
              <h2 className="text-base font-semibold text-fg">Шаги воронки</h2>
              <div className="flex items-center gap-3 text-xs">
                <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 bg-indigo-400 rounded" /> Общие</span>
                <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 bg-orange-400 rounded" /> Рекламные</span>
                <span className="text-fg-muted">кликни на шаг → детализация по дням</span>
              </div>
            </div>

            <div className="flex flex-col">
              {steps.map((step, idx) => {
                const Icon = step.icon
                const width = Math.max(2, (step.value / maxValue) * 100)
                const isActive = drillStep === step.key
                return (
                  <div key={step.key}>
                    {/* конверсия между шагами — КРУПНО */}
                    {idx > 0 && step.conv != null && (
                      <div className="flex items-center gap-2 my-1 ml-12">
                        <ArrowDown className="w-4 h-4 text-fg-muted" />
                        <span className="text-base font-semibold text-fg">{step.conv}%</span>
                        <span className="text-sm text-fg-muted">{step.convLabel}</span>
                      </div>
                    )}
                    <button onClick={() => setDrillStep(isActive ? null : step.key)}
                      className={cn(
                        'flex items-center gap-3 group text-left w-full py-2 rounded-md',
                        isActive && 'ring-2 ring-fg/20 bg-bg-subtle/40 px-2 -mx-2',
                      )}
                    >
                      <div className="w-9 h-9 rounded-lg border bg-bg-subtle/30 flex items-center justify-center shrink-0">
                        <Icon className="w-4 h-4 text-fg-muted" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex justify-between items-baseline mb-1">
                          <span className="text-sm font-medium text-fg">{step.label}</span>
                          <div className="flex items-center gap-3">
                            {/* "Рекламные" — пока нет per-step breakdown по рекламе → пометка */}
                            <span className="text-xs text-fg-subtle">общие</span>
                            <span className="text-lg font-semibold text-fg tabular-nums">{formatNumber(step.value)}</span>
                          </div>
                        </div>
                        <div className="relative h-3 rounded-full bg-bg-subtle overflow-hidden">
                          <div className={cn('h-full rounded-full transition-all', step.color)} style={{ width: `${width}%` }} />
                        </div>
                      </div>
                    </button>
                  </div>
                )
              })}
            </div>
          </Card>

          {/* === РЕКЛАМА: типы кампаний + total spend + ДРР === */}
          <Card className="p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-base font-semibold text-fg flex items-center gap-2">
                <Megaphone className="w-4 h-4 text-fg-muted" />
                Рекламные расходы
              </h2>
              <div className="text-xs text-fg-muted">
                Всего: <strong className="text-fg tabular-nums">{formatCurrency(ad?.total_spend ?? 0)}</strong>
                {ad?.drr_pct != null && <> · ДРР <strong className="text-fg tabular-nums">{ad.drr_pct}%</strong></>}
              </div>
            </div>
            {!ad?.has_data ? (
              <div className="rounded-md border border-amber-200 bg-amber-50/60 px-3 py-3 flex items-start gap-2 text-sm text-amber-900">
                <Lock className="w-4 h-4 mt-0.5 shrink-0" />
                <div>
                  <strong>Рекламных расходов за период не найдено.</strong>
                  <p className="text-xs mt-0.5">
                    Если у вас есть кампании в Performance API — настройте OAuth ключи кабинета и подождите синк Beat.
                    Если используется только Promotion-сервис Ozon (трафареты/продвижение/CPA) — данные подтягиваются из transactions автоматически.
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                {ad.breakdown.map((b) => (
                  <div key={b.op_type} className="flex items-center gap-3">
                    <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-orange-50 text-orange-700 shrink-0">
                      {b.model}
                    </span>
                    <span className="text-sm text-fg flex-1 truncate">{b.label}</span>
                    <div className="w-32 h-2 bg-bg-subtle rounded-full overflow-hidden">
                      <div className="h-full bg-orange-400 rounded-full" style={{ width: `${Math.min(100, b.pct_of_total)}%` }} />
                    </div>
                    <span className="text-sm font-mono tabular-nums w-24 text-right">{formatCurrency(b.amount)}</span>
                    <span className="text-xs text-fg-muted tabular-nums w-12 text-right">{b.pct_of_total}%</span>
                  </div>
                ))}
                <p className="text-xs text-fg-muted mt-3 pt-3 border-t border-border-subtle">
                  <strong>CPC</strong> — за клик · <strong>CPA</strong> — за заказ (% с состоявшегося) · <strong>FIXED</strong> — фикс. оплата
                </p>
              </div>
            )}
          </Card>

          {/* === DRILL-DOWN === */}
          {drillStep && (
            <Card className="p-5">
              <h3 className="text-base font-semibold text-fg mb-3">{DRILL_TITLES[drillStep]}</h3>
              {dailyLoading && (daily?.length ?? 0) === 0 ? (
                <div className="py-8 flex justify-center"><Loader2 className="w-5 h-5 animate-spin" /></div>
              ) : (daily?.length ?? 0) === 0 ? (
                <p className="text-fg-muted text-sm">Нет данных за период</p>
              ) : (
                <DrillTable step={drillStep} rows={(daily || []).slice().reverse().slice(0, 60)}
                  onRowClick={(d) => navigate(`/orders?date_from=${d}&date_to=${d}`)} />
              )}
            </Card>
          )}

          {/* === BEST/WORST DAYS === */}
          <Card className="p-5">
            <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
              <div>
                <h3 className="text-base font-semibold text-fg">Лучшие и худшие дни</h3>
                <p className="text-xs text-fg-muted mt-0.5">{BW_LABELS[bwMetric]}</p>
              </div>
              <div className="flex gap-1.5">
                {(['overall', 'cart', 'order', 'delivery'] as const).map((m) => (
                  <button key={m} onClick={() => setBwMetric(m)} className={cn(
                    'px-2.5 py-1 rounded text-xs border',
                    bwMetric === m ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle',
                  )}>
                    {m === 'overall' ? 'Сквозная' : m === 'cart' ? 'В корзину' : m === 'order' ? 'В заказ' : 'Выкуп'}
                  </button>
                ))}
              </div>
            </div>
            {bestWorst && (bestWorst.best.length > 0 || bestWorst.worst.length > 0) ? (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <BWTable title="Лучшие" Icon={TrendingUp} iconColor="text-emerald-700"
                  rows={bestWorst.best} from_label={bestWorst.from_label} to_label={bestWorst.to_label}
                  highlightColor="text-emerald-700" />
                <BWTable title="Худшие" Icon={TrendingDown} iconColor="text-rose-700"
                  rows={bestWorst.worst} from_label={bestWorst.from_label} to_label={bestWorst.to_label}
                  highlightColor="text-rose-700" />
              </div>
            ) : (
              <p className="text-fg-muted text-sm text-center py-4">Недостаточно данных для топ-5</p>
            )}
          </Card>

          <FunnelInsights days={days} productId={productId || undefined}
                          cabinetIds={selectedCabinetIds} />
        </>
      )}
    </div>
  )
}

function FunnelSkeleton() {
  return (
    <>
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <Card key={i} className="p-4">
            <div className="h-3 w-24 bg-bg-subtle rounded animate-pulse mb-2" />
            <div className="h-6 w-16 bg-bg-subtle rounded animate-pulse" />
          </Card>
        ))}
      </div>
      <Card className="p-5">
        <div className="h-4 w-32 bg-bg-subtle rounded animate-pulse mb-4" />
        <div className="flex flex-col gap-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-bg-subtle animate-pulse shrink-0" />
              <div className="flex-1">
                <div className="h-4 w-32 bg-bg-subtle rounded animate-pulse mb-2" />
                <div className="h-3 w-full bg-bg-subtle rounded animate-pulse" />
              </div>
            </div>
          ))}
        </div>
      </Card>
    </>
  )
}

function DrillTable({
  step, rows, onRowClick,
}: {
  step: Exclude<DrillStep, null>
  rows: FunnelDaily[]
  onRowClick: (date: string) => void
}) {
  if (step === 'impressions') {
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-bg-subtle/50">
            <tr className="text-left text-xs text-fg-muted uppercase">
              <th className="py-2 px-3">дата</th>
              <th className="py-2 px-3 text-right">всего</th>
              <th className="py-2 px-3 text-right">поиск</th>
              <th className="py-2 px-3 text-right">карточка</th>
              <th className="py-2 px-3 text-right">доля поиска</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {rows.map((r) => {
              const sharePoisk = r.impressions > 0 ? (r.impressions_search / r.impressions) * 100 : 0
              return (
                <tr key={r.date} className="hover:bg-bg-subtle/40 cursor-pointer" onClick={() => onRowClick(r.date)}>
                  <td className="py-2 px-3 font-mono text-xs">{formatDate(r.date)}</td>
                  <td className="py-2 px-3 text-right tabular-nums font-semibold">{formatNumber(r.impressions)}</td>
                  <td className="py-2 px-3 text-right tabular-nums">{formatNumber(r.impressions_search)}</td>
                  <td className="py-2 px-3 text-right tabular-nums">{formatNumber(r.impressions_pdp)}</td>
                  <td className="py-2 px-3 text-right tabular-nums text-fg-muted">{sharePoisk.toFixed(1)}%</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    )
  }
  if (step === 'clicks') {
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-bg-subtle/50">
            <tr className="text-left text-xs text-fg-muted uppercase">
              <th className="py-2 px-3">дата</th>
              <th className="py-2 px-3 text-right">показы</th>
              <th className="py-2 px-3 text-right">клики</th>
              <th className="py-2 px-3 text-right">CTR</th>
              <th className="py-2 px-3 text-right">в корзину</th>
              <th className="py-2 px-3 text-right">клик → корзина</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {rows.map((r) => {
              const c2cart = r.clicks > 0 ? (r.to_cart / r.clicks) * 100 : 0
              return (
                <tr key={r.date} className="hover:bg-bg-subtle/40 cursor-pointer" onClick={() => onRowClick(r.date)}>
                  <td className="py-2 px-3 font-mono text-xs">{formatDate(r.date)}</td>
                  <td className="py-2 px-3 text-right tabular-nums">{formatNumber(r.impressions)}</td>
                  <td className="py-2 px-3 text-right tabular-nums font-semibold">{formatNumber(r.clicks)}</td>
                  <td className="py-2 px-3 text-right tabular-nums font-semibold">{r.ctr_pct != null ? `${r.ctr_pct}%` : '—'}</td>
                  <td className="py-2 px-3 text-right tabular-nums">{formatNumber(r.to_cart)}</td>
                  <td className="py-2 px-3 text-right tabular-nums text-fg-muted">{c2cart.toFixed(2)}%</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    )
  }
  if (step === 'to_cart') {
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-bg-subtle/50">
            <tr className="text-left text-xs text-fg-muted uppercase">
              <th className="py-2 px-3">дата</th>
              <th className="py-2 px-3 text-right">показы</th>
              <th className="py-2 px-3 text-right">в корзину</th>
              <th className="py-2 px-3 text-right">из поиска</th>
              <th className="py-2 px-3 text-right">с карточки</th>
              <th className="py-2 px-3 text-right">конверсия в корзину</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {rows.map((r) => (
              <tr key={r.date} className="hover:bg-bg-subtle/40 cursor-pointer" onClick={() => onRowClick(r.date)}>
                <td className="py-2 px-3 font-mono text-xs">{formatDate(r.date)}</td>
                <td className="py-2 px-3 text-right tabular-nums">{formatNumber(r.impressions)}</td>
                <td className="py-2 px-3 text-right tabular-nums font-semibold">{formatNumber(r.to_cart)}</td>
                <td className="py-2 px-3 text-right tabular-nums text-fg-muted">{formatNumber(r.to_cart_search)}</td>
                <td className="py-2 px-3 text-right tabular-nums text-fg-muted">{formatNumber(r.to_cart_pdp)}</td>
                <td className="py-2 px-3 text-right tabular-nums font-semibold">
                  {r.cart_conv_pct != null ? `${r.cart_conv_pct}%` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  if (step === 'orders') {
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-bg-subtle/50">
            <tr className="text-left text-xs text-fg-muted uppercase">
              <th className="py-2 px-3">дата</th>
              <th className="py-2 px-3 text-right">в корзину</th>
              <th className="py-2 px-3 text-right">заказы шт</th>
              <th className="py-2 px-3 text-right">выручка</th>
              <th className="py-2 px-3 text-right">конверсия в заказ</th>
              <th className="py-2 px-3 text-right">ср. чек</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {rows.map((r) => {
              const aov = r.orders > 0 ? r.revenue / r.orders : 0
              return (
                <tr key={r.date} className="hover:bg-bg-subtle/40 cursor-pointer" onClick={() => onRowClick(r.date)}>
                  <td className="py-2 px-3 font-mono text-xs">{formatDate(r.date)}</td>
                  <td className="py-2 px-3 text-right tabular-nums">{formatNumber(r.to_cart)}</td>
                  <td className="py-2 px-3 text-right tabular-nums font-semibold">{formatNumber(r.orders)}</td>
                  <td className="py-2 px-3 text-right tabular-nums">{formatCurrency(r.revenue)}</td>
                  <td className="py-2 px-3 text-right tabular-nums font-semibold">
                    {r.order_conv_pct != null ? `${r.order_conv_pct}%` : '—'}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-fg-muted">{formatCurrency(aov)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    )
  }
  // delivered
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-bg-subtle/50">
          <tr className="text-left text-xs text-fg-muted uppercase">
            <th className="py-2 px-3">дата</th>
            <th className="py-2 px-3 text-right">заказы</th>
            <th className="py-2 px-3 text-right">доставлено</th>
            <th className="py-2 px-3 text-right">возвраты</th>
            <th className="py-2 px-3 text-right">выкуп %</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {rows.map((r) => (
            <tr key={r.date} className="hover:bg-bg-subtle/40 cursor-pointer" onClick={() => onRowClick(r.date)}>
              <td className="py-2 px-3 font-mono text-xs">{formatDate(r.date)}</td>
              <td className="py-2 px-3 text-right tabular-nums">{formatNumber(r.orders)}</td>
              <td className="py-2 px-3 text-right tabular-nums font-semibold">{formatNumber(r.delivered)}</td>
              <td className="py-2 px-3 text-right tabular-nums text-rose-700">{formatNumber(r.returns)}</td>
              <td className="py-2 px-3 text-right tabular-nums font-semibold">
                {r.delivery_conv_pct != null ? `${r.delivery_conv_pct}%` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BWTable({
  title, Icon, iconColor, rows, from_label, to_label, highlightColor,
}: {
  title: string
  Icon: React.ComponentType<{ className?: string }>
  iconColor: string
  rows: BestWorstDay[]
  from_label: string
  to_label: string
  highlightColor: string
}) {
  return (
    <div>
      <h4 className={cn('text-base font-semibold flex items-center gap-2 mb-3', iconColor)}>
        <Icon className="w-4 h-4" /> {title}
      </h4>
      <table className="w-full text-sm">
        <thead className="bg-bg-subtle/50">
          <tr className="text-left text-xs text-fg-muted uppercase">
            <th className="py-2 px-2.5">дата</th>
            <th className="py-2 px-2.5 text-right">{from_label}</th>
            <th className="py-2 px-2.5 text-right">{to_label}</th>
            <th className="py-2 px-2.5 text-right">конверсия</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {rows.map((d) => (
            <tr key={d.date}>
              <td className="py-2 px-2.5 font-mono text-xs">{formatDate(d.date)}</td>
              <td className="py-2 px-2.5 text-right tabular-nums">{formatNumber(d.from_value)}</td>
              <td className="py-2 px-2.5 text-right tabular-nums">{formatNumber(d.to_value)}</td>
              <td className={cn('py-2 px-2.5 text-right tabular-nums font-semibold', highlightColor)}>{d.conv_pct}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ConvCard({ label, curr, prev, tooltip }: {
  label: string; curr: number | null; prev?: number | null; tooltip?: string
}) {
  const delta = curr != null && prev != null ? curr - prev : null
  return (
    <Card className="p-3" title={tooltip}>
      <p className="text-[10px] font-medium text-fg-muted uppercase tracking-wider truncate">{label}</p>
      <p className="text-[18px] leading-tight font-semibold text-fg mt-1 tabular-nums">
        {curr != null ? `${curr}%` : '—'}
      </p>
      {delta != null && (
        <p className={cn(
          'text-[10px] mt-1 tabular-nums inline-flex items-center gap-0.5',
          delta >= 0 ? 'text-emerald-700' : 'text-rose-700',
        )}>
          {delta >= 0 ? <ArrowUpRight className="w-2.5 h-2.5" /> : <ArrowDownRight className="w-2.5 h-2.5" />}
          {delta >= 0 ? '+' : ''}{delta.toFixed(2)} п.п.
        </p>
      )}
    </Card>
  )
}
