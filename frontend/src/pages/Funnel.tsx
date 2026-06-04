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
import { DayExplanationDrawer } from '@/components/DayExplanationDrawer'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { DateRangeBar } from '@/components/DateRangeBar'
import { useCabinetStore } from '@/stores/cabinet'
import { AskAIButton } from '@/components/AskAIButton'

interface FunnelKPI {
  impressions: number
  impressions_search?: number       // Показы в поиске (для 6-ступенчатой воронки Ozon)
  card_visits?: number              // Посещения карточки (= clicks для legacy)
  clicks: number
  to_cart: number
  orders: number
  delivered: number
  revenue: number
  search_to_card_pct?: number | null   // конверсия из поиска в карточку (~22% у Ozon)
  card_to_cart_pct?: number | null     // конверсия карточка → корзина (~9% у Ozon)
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
  drr_pct: number | null            // legacy = drr_overall_pct
  drr_advertising_pct: number | null  // как у Ozon — spend/ad_revenue
  drr_overall_pct: number | null      // spend/total_revenue (доля в обороте)
  ad_revenue: number
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

interface AverageDay {
  date: string         // "средний из N дн"
  from_value: number
  to_value: number
  conv_pct: number     // средняя конверсия
  median_pct: number   // медианная (устойчива к выбросам)
  revenue: number
  days_count: number
}

interface BestWorstResp {
  best: BestWorstDay[]
  worst: BestWorstDay[]
  average: AverageDay | null
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

type DrillStep = 'impressions' | 'impressions_search' | 'clicks' | 'to_cart' | 'orders' | 'delivered' | null
type BWMetric = 'overall' | 'cart' | 'order' | 'delivery'

const DRILL_TITLES: Record<Exclude<DrillStep, null>, string> = {
  impressions: 'Детализация: Показы по дням',
  impressions_search: 'Детализация: Показы в поиске по дням',
  clicks: 'Детализация: Посещения карточки по дням',
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
  const dateFrom = params.get('date_from')
  const dateTo = params.get('date_to')
  // Power BI-style multi-select: URL держит массив p=id1&p=id2&...
  const productIds = params.getAll('p')
  // Для обратной совместимости (старый код передавал один)
  const productId = productIds[0] || ''
  const compare = (params.get('cmp') || 'prev_period') as 'none' | 'prev_period' | 'year_ago'
  const archiveFilter = (params.get('arch') || 'active') as 'active' | 'archived' | 'all'
  const [productSearch, setProductSearch] = useState('')
  const [drillStep, setDrillStep] = useState<DrillStep>(null)
  const [bwMetric, setBwMetric] = useState<BWMetric>('order')
  const [explainDate, setExplainDate] = useState<string | null>(null)

  const updateParam = (k: string, v: string | undefined) => {
    const p = new URLSearchParams(params)
    if (v) p.set(k, v); else p.delete(k)
    setParams(p, { replace: true })
  }

  const toggleProductId = (id: string) => {
    const p = new URLSearchParams(params)
    const current = p.getAll('p')
    if (current.includes(id)) {
      // снять выбор
      p.delete('p')
      current.filter((x) => x !== id).forEach((x) => p.append('p', x))
    } else {
      p.append('p', id)
    }
    setParams(p, { replace: true })
  }

  const clearAllProducts = () => {
    const p = new URLSearchParams(params)
    p.delete('p')
    setParams(p, { replace: true })
  }

  const selectAllVisible = (ids: string[]) => {
    const p = new URLSearchParams(params)
    p.delete('p')
    ids.forEach((id) => p.append('p', id))
    setParams(p, { replace: true })
  }

  const { data: products } = useQuery<ProductLite[]>({
    // Селектор товаров воронки фильтруется по тем же кабинетам что и метрики.
    // Раньше брали все товары /products/ без cabinet_ids → юзер видел чужие
    // (например Жираф из home хотя выбран презент).
    queryKey: ['products', 'lite', selectedCabinetIds],
    queryFn: async () => {
      const p = new URLSearchParams()
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      const qs = p.toString()
      return (await api.get(qs ? `/products/?${qs}` : '/products/')).data as ProductLite[]
    },
  })

  const filteredProducts = useMemo(() => {
    if (!products) return []
    const s = productSearch.trim().toLowerCase()
    return products
      .filter((p) => {
        if (archiveFilter === 'active' && p.is_archived) return false
        if (archiveFilter === 'archived' && !p.is_archived) return false
        return true
      })
      .filter((p) => !s || p.name.toLowerCase().includes(s) || p.offer_id.toLowerCase().includes(s))
  }, [products, productSearch, archiveFilter])

  // Сборка query параметров: множественный ?p= + cabinet_ids
  const buildQs = (extra: Record<string, string> = {}): string => {
    const p = new URLSearchParams(extra)
    if (dateFrom && dateTo) {
      p.set('date_from', dateFrom); p.set('date_to', dateTo)
    } else {
      p.set('days', String(days))
    }
    productIds.forEach((id) => p.append('product_ids', id))
    selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
    return p.toString()
  }

  const { data, isLoading, isFetching } = useQuery<FunnelV2Resp>({
    queryKey: ['funnel-v2', selectedCabinetIds, days, dateFrom, dateTo, productIds.join(','), compare],
    queryFn: async () =>
      (await api.get(`/analytics/funnel/v2/?${buildQs({ compare })}`)).data,
  })

  const { data: daily, isFetching: dailyLoading } = useQuery<FunnelDaily[]>({
    queryKey: ['funnel-v2', 'daily', selectedCabinetIds, days, dateFrom, dateTo, productIds.join(',')],
    queryFn: async () => (await api.get(`/analytics/funnel/v2/daily?${buildQs()}`)).data,
    enabled: drillStep !== null,
  })

  const { data: bestWorst } = useQuery<BestWorstResp>({
    queryKey: ['funnel-v2', 'bw', selectedCabinetIds, days, dateFrom, dateTo, productIds.join(','), bwMetric],
    queryFn: async () =>
      (await api.get(`/analytics/funnel/v2/best-worst-days?${buildQs({ metric: bwMetric })}`)).data,
  })

  const kpi = data?.kpi
  const prev = data?.prev_kpi
  const ad = data?.ad
  const maxValue = useMemo(() => {
    if (!kpi) return 1
    return Math.max(1, kpi.impressions, (kpi as any).impressions_search ?? 0,
      kpi.clicks, kpi.to_cart, kpi.orders, kpi.delivered)
  }, [kpi])

  // 6 ступеней по эталону Ozon (Аналитика → Воронка продаж):
  //   Показы всего → [конверсия поиск→карточка] → Посещения карточки →
  //   [карточка→корзина] → Корзина → [корзина→заказ] → Заказы →
  //   [заказ→выкуп] → Доставлено
  // Между шагами — ↳ конверсия отдельной строкой.
  const steps = useMemo(() => {
    if (!kpi) return []
    const k = kpi as any
    return [
      { key: 'impressions'        as const, label: 'Показы всего',           icon: Eye,                value: kpi.impressions,             conv: null,                          convLabel: null,                  color: 'bg-slate-400'   },
      { key: 'impressions_search' as const, label: 'Показы в поиске',        icon: Eye,                value: k.impressions_search ?? 0,    conv: null,                          convLabel: 'из общих показов',    color: 'bg-indigo-400'  },
      { key: 'clicks'             as const, label: 'Посещения карточки',     icon: MousePointerClick,  value: kpi.clicks,                   conv: k.search_to_card_pct ?? kpi.ctr_pct, convLabel: 'поиск → карточка', color: 'bg-blue-400'    },
      { key: 'to_cart'            as const, label: 'В корзину',              icon: ShoppingCart,       value: kpi.to_cart,                  conv: k.card_to_cart_pct ?? kpi.click_to_cart_pct, convLabel: 'карточка → корзина', color: 'bg-violet-400'  },
      { key: 'orders'             as const, label: 'Заказы',                 icon: ShoppingBag,        value: kpi.orders,                   conv: kpi.order_conv_pct,            convLabel: 'корзина → заказ',     color: 'bg-emerald-400' },
      { key: 'delivered'          as const, label: 'Доставлено',             icon: CheckCircle2,       value: kpi.delivered,                conv: kpi.delivery_conv_pct,         convLabel: 'заказ → выкуп',       color: 'bg-amber-400'   },
    ]
  }, [kpi])

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Воронка</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            {data?.product_name ? <>SKU: <strong>{data.product_name}</strong></> : 'По всему кабинету'} · {data?.period_from} … {data?.period_to}
          </p>
        </div>
        <AskAIButton
          context={{
            type: 'chart',
            source_page: 'funnel',
            source_label: productId ? `Воронка — ${data?.product_name || 'SKU'}` : 'Воронка по кабинету',
            metrics: ['impressions', 'card_visits', 'to_cart', 'orders', 'delivered', 'revenue', 'drr_advertising_pct', 'drr_overall_pct'],
            period: data ? { from: data.period_from, to: data.period_to } : undefined,
            product_id: productId || undefined,
            product_name: data?.product_name || undefined,
            cabinet_ids: selectedCabinetIds,
          }}
          question={productId
            ? "Где узкое место воронки этого SKU? Что чинить в первую очередь?"
            : "Где главная утечка в воронке? Какие SKU тянут вниз?"}
          variant="solid"
        />
      </div>

      {/* TOOLBAR */}
      <Card className="p-3 flex flex-wrap items-center gap-2">
        <DateRangeBar days={days} onChange={(r) => {
          const p = new URLSearchParams(params)
          p.set('days', String(r.days))
          if (r.dateFrom && r.dateTo) {
            p.set('date_from', r.dateFrom); p.set('date_to', r.dateTo)
          } else {
            p.delete('date_from'); p.delete('date_to')
          }
          setParams(p, { replace: true })
        }} />
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

      {/* PRODUCT SELECTOR — Power BI-style multi-select со списком чекбоксов */}
      <Card className="p-4">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h3 className="text-sm font-semibold text-fg">
            Товары
            {productIds.length > 0 && (
              <span className="ml-2 text-xs font-normal text-fg-muted">
                выбрано {productIds.length}
              </span>
            )}
          </h3>
          <div className="flex items-center gap-2 flex-wrap">
            {/* Архив-фильтр */}
            <div className="flex border border-border-subtle rounded-md overflow-hidden">
              {(['active', 'archived', 'all'] as const).map((k) => (
                <button key={k} onClick={() => updateParam('arch', k)} className={cn(
                  'px-2 py-1 text-[11px]',
                  archiveFilter === k ? 'bg-fg text-bg' : 'text-fg-muted hover:bg-bg-subtle',
                )}>
                  {k === 'active' ? 'Активные' : k === 'archived' ? 'Архив' : 'Все'}
                </button>
              ))}
            </div>
            <button onClick={() => selectAllVisible(filteredProducts.map((x) => x.id))}
                    className="text-xs text-fg-muted hover:text-fg border border-border-subtle rounded px-2 py-1">
              Выбрать все
            </button>
            {productIds.length > 0 && (
              <button onClick={clearAllProducts}
                      className="text-xs text-fg-muted hover:text-fg">
                × снять выбор
              </button>
            )}
          </div>
        </div>
        <div className="relative mb-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-fg-subtle" />
          <Input value={productSearch} onChange={(e) => setProductSearch(e.target.value)}
            placeholder="название или offer_id" className="pl-9" />
        </div>
        <div className="border border-border-subtle rounded-md max-h-[260px] overflow-y-auto divide-y divide-border-subtle">
          {filteredProducts.length === 0 && (
            <div className="text-sm text-fg-muted py-4 text-center">Нет товаров для фильтра</div>
          )}
          {filteredProducts.map((p) => {
            const checked = productIds.includes(p.id)
            return (
              <label
                key={p.id}
                title={`${p.name}\nОстаток: ${p.total_stock} шт${p.is_archived ? '\nАРХИВ' : ''}`}
                className={cn(
                  'flex items-center gap-2 px-3 py-1.5 text-xs cursor-pointer hover:bg-bg-subtle/40',
                  checked && 'bg-indigo-50/50',
                  p.is_archived && 'opacity-60',
                )}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleProductId(p.id)}
                  className="w-3.5 h-3.5 accent-indigo-600 shrink-0"
                />
                {p.image_url ? (
                  <img src={p.image_url} alt="" className="w-5 h-5 rounded object-cover shrink-0" />
                ) : (
                  <ImageIcon className="w-4 h-4 shrink-0 text-fg-subtle" />
                )}
                <span
                  className={cn('w-1.5 h-1.5 rounded-full shrink-0', stockColor(p.total_stock))}
                  aria-hidden
                />
                <span className="flex-1 truncate text-fg">{p.name}</span>
                <span className="text-fg-muted font-mono shrink-0">{p.offer_id}</span>
                <span className="text-fg-subtle tabular-nums shrink-0 w-10 text-right">{p.total_stock}</span>
                {p.is_archived && (
                  <span className="text-[9px] px-1 rounded bg-slate-200 text-slate-600 shrink-0">АРХИВ</span>
                )}
              </label>
            )
          })}
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
          {/* === KPI (Ozon-эталон + раздельный ДРР) === */}
          <div className={cn('grid grid-cols-2 lg:grid-cols-6 gap-3 transition-opacity', isFetching && 'opacity-50')}>
            <ConvCard label="Сквозная" curr={kpi!.overall_conv_pct} prev={prev?.overall_conv_pct} />
            <ConvCard label="Поиск → карточка"
              curr={kpi!.search_to_card_pct ?? kpi!.ctr_pct}
              prev={prev?.search_to_card_pct ?? prev?.ctr_pct}
              tooltip="Конверсия из поиска/каталога в карточку. Эталон Ozon: ~22%." />
            <ConvCard label="Карточка → корзина"
              curr={kpi!.card_to_cart_pct ?? kpi!.click_to_cart_pct}
              prev={prev?.card_to_cart_pct ?? prev?.click_to_cart_pct}
              tooltip="Конверсия посещений карточки в добавления в корзину. Эталон Ozon: ~9%." />
            <ConvCard label="Корзина → заказ" curr={kpi!.order_conv_pct} prev={prev?.order_conv_pct}
              tooltip="Эталон Ozon: ~35%." />
            <ConvCard label="Выкуп" curr={kpi!.delivery_conv_pct} prev={prev?.delivery_conv_pct}
              tooltip="Заказ → доставлено. Эталон Ozon: ~90%." />
            <ConvCard label="ДРР рекламный"
              curr={ad?.drr_advertising_pct ?? null} prev={null}
              tooltip={`Spend(PA) / выручка из рекламы (ad_statistics). Это та же формула что у Ozon в кабинете. ad_revenue: ${ad?.ad_revenue?.toLocaleString() || 0}₽`} />
          </div>

          {/* === Два ДРР отдельно — юзер: «Ozon показывает 1.1% рекл., наш был 2.94% общий» === */}
          {ad?.has_data && (
            <Card className="p-3 flex flex-wrap items-stretch gap-4 text-xs">
              <div className="flex-1 min-w-[200px]">
                <div className="text-fg-muted uppercase text-[10px] tracking-wider">ДРР рекламный (как в кабинете Ozon)</div>
                <div className="text-lg font-semibold text-fg tabular-nums">
                  {ad.drr_advertising_pct !== null ? `${ad.drr_advertising_pct.toFixed(2)}%` : '—'}
                </div>
                <div className="text-fg-subtle mt-0.5">
                  Эффективность рекламы как канала: расход / выручка ИЗ рекламы ({formatCurrency(ad.ad_revenue || 0)})
                </div>
              </div>
              <div className="flex-1 min-w-[200px]">
                <div className="text-fg-muted uppercase text-[10px] tracking-wider">ДРР общий</div>
                <div className="text-lg font-semibold text-fg tabular-nums">
                  {ad.drr_overall_pct !== null ? `${ad.drr_overall_pct.toFixed(2)}%` : '—'}
                </div>
                <div className="text-fg-subtle mt-0.5">
                  Доля рекламы в обороте: расход / ВСЯ выручка (вкл. органику)
                </div>
              </div>
            </Card>
          )}

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
              <>
                {/* Средний день — норма для сравнения. Юзер: «есть лучшие/худшие, где средняя?» */}
                {bestWorst.average && (
                  <div className="rounded-md border border-indigo-200 bg-indigo-50/50 px-4 py-3 mb-4 text-sm flex flex-wrap items-center gap-4">
                    <div>
                      <div className="text-[10px] uppercase tracking-wider text-indigo-700 font-semibold">
                        Средний день за период
                      </div>
                      <div className="text-fg-muted text-[11px] mt-0.5">
                        Из {bestWorst.average.days_count} дней с данными. Сравни лучший/худший с этим — отклонение покажет «норму».
                      </div>
                    </div>
                    <div className="ml-auto flex gap-5 text-fg">
                      <div>
                        <div className="text-[10px] text-fg-muted uppercase">средн. {bestWorst.from_label}</div>
                        <div className="tabular-nums font-medium">{formatNumber(bestWorst.average.from_value)}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-fg-muted uppercase">средн. {bestWorst.to_label}</div>
                        <div className="tabular-nums font-medium">{formatNumber(bestWorst.average.to_value)}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-fg-muted uppercase">средняя конв.</div>
                        <div className="tabular-nums font-semibold text-indigo-700">{bestWorst.average.conv_pct.toFixed(2)}%</div>
                      </div>
                      <div title="Медиана устойчивее к выбросам, чем среднее">
                        <div className="text-[10px] text-fg-muted uppercase">медиана</div>
                        <div className="tabular-nums text-fg-muted">{bestWorst.average.median_pct.toFixed(2)}%</div>
                      </div>
                    </div>
                  </div>
                )}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <BWTable title="Лучшие" Icon={TrendingUp} iconColor="text-emerald-700"
                    rows={bestWorst.best} from_label={bestWorst.from_label} to_label={bestWorst.to_label}
                    highlightColor="text-emerald-700"
                    avgConv={bestWorst.average?.conv_pct ?? null}
                    onExplain={setExplainDate} />
                  <BWTable title="Худшие" Icon={TrendingDown} iconColor="text-rose-700"
                    rows={bestWorst.worst} from_label={bestWorst.from_label} to_label={bestWorst.to_label}
                    highlightColor="text-rose-700"
                    avgConv={bestWorst.average?.conv_pct ?? null}
                    onExplain={setExplainDate} />
                </div>
              </>
            ) : (
              <p className="text-fg-muted text-sm text-center py-4">Недостаточно данных для топ-5</p>
            )}
          </Card>

          <FunnelInsights days={days} productIds={productIds}
                          cabinetIds={selectedCabinetIds} />
        </>
      )}

      {/* «Объяснение дня» drawer — открывается при клике на день в best/worst таблицах */}
      <DayExplanationDrawer
        productId={productIds[0] || null}
        date={explainDate}
        cabinetIds={selectedCabinetIds}
        open={!!explainDate}
        onClose={() => setExplainDate(null)}
      />
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
              <th className="py-2 px-3 text-right">% в карточку</th>
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
  title, Icon, iconColor, rows, from_label, to_label, highlightColor, avgConv, onExplain,
}: {
  title: string
  Icon: React.ComponentType<{ className?: string }>
  iconColor: string
  rows: BestWorstDay[]
  from_label: string
  to_label: string
  highlightColor: string
  avgConv: number | null
  onExplain?: (date: string) => void
}) {
  return (
    <div>
      <h4 className={cn('text-base font-semibold flex items-center gap-2 mb-3', iconColor)}>
        <Icon className="w-4 h-4" /> {title}
        {onExplain && (
          <span className="text-[10px] text-fg-subtle font-normal ml-auto">тык в день → объяснение</span>
        )}
      </h4>
      <table className="w-full text-sm">
        <thead className="bg-bg-subtle/50">
          <tr className="text-left text-xs text-fg-muted uppercase">
            <th className="py-2 px-2.5">дата</th>
            <th className="py-2 px-2.5 text-right">{from_label}</th>
            <th className="py-2 px-2.5 text-right">{to_label}</th>
            <th className="py-2 px-2.5 text-right">конверсия</th>
            {avgConv !== null && <th className="py-2 px-2.5 text-right text-[10px]">δ vs средн.</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {rows.map((d) => {
            const delta = avgConv !== null ? d.conv_pct - avgConv : null
            return (
              <tr
                key={d.date}
                className={cn(onExplain && 'hover:bg-bg-subtle/60 cursor-pointer')}
                onClick={onExplain ? () => onExplain(d.date) : undefined}
                title={onExplain ? 'Открыть объяснение дня' : undefined}
              >
                <td className="py-2 px-2.5 font-mono text-xs">{formatDate(d.date)}</td>
                <td className="py-2 px-2.5 text-right tabular-nums">{formatNumber(d.from_value)}</td>
                <td className="py-2 px-2.5 text-right tabular-nums">{formatNumber(d.to_value)}</td>
                <td className={cn('py-2 px-2.5 text-right tabular-nums font-semibold', highlightColor)}>{d.conv_pct}%</td>
                {delta !== null && (
                  <td className={cn('py-2 px-2.5 text-right tabular-nums text-xs',
                    delta >= 0 ? 'text-emerald-600' : 'text-rose-600')}>
                    {delta >= 0 ? '+' : ''}{delta.toFixed(2)} п.п.
                  </td>
                )}
              </tr>
            )
          })}
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
