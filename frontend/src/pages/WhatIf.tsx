/**
 * «Что если» симулятор сценариев.
 * Слева — реальные β из данных юзера + база. Справа — 3 сценария рядом.
 *
 * Принцип юзера: где β надёжный (R²>0.3) — используем как факт.
 * Где данных мало — слайдер «твоя гипотеза», не подсовываем дефолт молча.
 */
import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Loader2, Sliders, TrendingUp, AlertTriangle, Info, Play } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { useProductFilter } from '@/stores/product_filter'

interface BetaPoint { beta: number | null; n: number; r2: number | null; confidence: string; note: string }
interface BetasResp {
  product: { id: string; name: string; offer_id: string; ozon_sku: number;
             cabinet_name: string; cost_price: number | null; seller_price: number | null;
             commission_pct: number }
  period: { days: number; from: string; to: string }
  base: { impressions: number; card_visits: number; to_cart: number; orders: number;
          delivered: number; ad_spend: number; ad_imp: number;
          avg_seller_price: number | null; avg_customer_price: number | null;
          cr_imp_to_visit: number | null; cr_visit_to_cart: number | null;
          cr_cart_to_order: number | null; cr_order_to_delivered: number | null }
  betas: {
    funnel: { imp_to_visits: BetaPoint; visits_to_cart: BetaPoint;
              cart_to_orders: BetaPoint; orders_to_delivered: BetaPoint;
              imp_to_orders_overall: BetaPoint }
    price: { seller_price_to_orders: BetaPoint; customer_price_to_orders: BetaPoint }
    ad: { ad_spend_to_imp: BetaPoint; ad_spend_to_orders: BetaPoint }
  }
}

interface Scenario {
  name: string
  ad_spend_pct: number
  seller_price_pct: number
  impressions_pct: number
  cr_cart_to_order_pct: number
  cost_pct: number
  spp_pct: number | null            // null = брать фактическое СПП из истории
  override_beta_price: number | null
  override_beta_customer_price: number | null
}

interface ScenarioResult {
  name: string
  impressions: number; card_visits: number; to_cart: number;
  orders: number; delivered: number
  seller_price: number; revenue: number; ad_spend: number
  drr_pct: number | null
  cost_total: number; commission_total: number; logistics_total: number
  acquiring_total: number; operating_profit: number
  tax_amount: number; net_profit: number; net_margin_pct: number | null
  delta_net_vs_base: number
  drivers_explanation: string[]
}

const EMPTY_SCENARIO = (name: string): Scenario => ({
  name,
  ad_spend_pct: 0, seller_price_pct: 0, impressions_pct: 0,
  cr_cart_to_order_pct: 0, cost_pct: 0,
  spp_pct: null, override_beta_price: null, override_beta_customer_price: null,
})

export function WhatIf() {
  const { selectedProductId, selectedProductName } = useProductFilter()
  const [scenarios, setScenarios] = useState<Scenario[]>([
    { ...EMPTY_SCENARIO('Сценарий A'), ad_spend_pct: 50 },
    { ...EMPTY_SCENARIO('Сценарий B'), seller_price_pct: -10, override_beta_price: -1.0 },
  ])

  const { data: betasData, isLoading: betasLoading } = useQuery<BetasResp>({
    queryKey: ['whatif', 'betas', selectedProductId],
    enabled: !!selectedProductId,
    queryFn: async () => (await api.get(`/whatif/betas/${selectedProductId}?days=60`)).data,
    staleTime: 5 * 60_000,
  })

  const simulate = useMutation({
    mutationFn: async () =>
      (await api.post('/whatif/simulate', { product_id: selectedProductId, days: 60, scenarios })).data,
  })

  useEffect(() => {
    if (betasData) simulate.mutate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [betasData, JSON.stringify(scenarios)])

  if (!selectedProductId) {
    return <WhatIfProductPicker />
  }

  if (betasLoading || !betasData) {
    return <Card className="p-8 flex justify-center"><Loader2 className="w-5 h-5 animate-spin" /></Card>
  }

  const sim = simulate.data as { scenarios: ScenarioResult[]; tax_regime_label: string; tax_rate_pct: number } | undefined
  const baseResult = sim?.scenarios[0]
  const customResults = sim?.scenarios.slice(1) || []

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight flex items-center gap-2">
          <Sliders className="w-7 h-7 text-purple-600" /> Симулятор «Что если»
        </h1>
        <p className="text-sm text-fg-muted mt-1.5">
          Реальные эластичности твоих данных + слайдеры. Сравни сценарии по чистой прибыли.
        </p>
        <div className="text-xs text-fg-subtle mt-1">
          Товар: <strong>{selectedProductName}</strong> ({betasData.product.offer_id} · {betasData.product.cabinet_name})
          · период анализа: {betasData.period.days} дней
        </div>
      </div>

      {/* β-блок (показываем что есть в данных) */}
      <Card className="p-4">
        <h3 className="text-sm font-semibold text-fg mb-3 flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-emerald-600" /> Эластичности из ТВОИХ данных (60 дней)
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <BetaCard label="Воронка: показы → заказы" b={betasData.betas.funnel.imp_to_orders_overall} />
          <BetaCard label="Воронка: показы → карточка" b={betasData.betas.funnel.imp_to_visits} />
          <BetaCard label="Воронка: карточка → корзина" b={betasData.betas.funnel.visits_to_cart} />
          <BetaCard label="Воронка: корзина → заказ" b={betasData.betas.funnel.cart_to_orders} />
          <BetaCard label="Цена продавца → заказы" b={betasData.betas.price.seller_price_to_orders} />
          <BetaCard label="СПП-цена покупателя → заказы" b={betasData.betas.price.customer_price_to_orders} />
          <BetaCard label="Реклама расход → показы" b={betasData.betas.ad.ad_spend_to_imp} />
          <BetaCard label="Реклама расход → заказы" b={betasData.betas.ad.ad_spend_to_orders} />
          <div className="rounded-md border border-blue-200 bg-blue-50/60 p-2.5 text-blue-900">
            <strong className="text-[11px]">Как читать:</strong>
            <ul className="mt-1 space-y-0.5 text-[11px]">
              <li>β = эластичность («+1% X → +β% Y»)</li>
              <li>R² ≥ 0.3 — связь надёжная (high)</li>
              <li>R² &lt; 0.1 — связи нет (low)</li>
              <li>n = точек данных</li>
            </ul>
          </div>
        </div>
      </Card>

      {/* Сценарии — 3 рядом (текущий + 2 кастомных) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Текущее */}
        <ScenarioColumn
          title="Текущее (как сейчас)"
          result={baseResult}
          isBase
          taxLabel={sim ? `${sim.tax_regime_label} ${sim.tax_rate_pct}%` : '—'}
        />
        {/* Кастомные */}
        {scenarios.map((sc, i) => (
          <ScenarioColumn
            key={i}
            title={sc.name}
            scenario={sc}
            onChange={(next) => {
              const arr = [...scenarios]; arr[i] = next; setScenarios(arr)
            }}
            result={customResults[i]}
            base={baseResult}
            taxLabel={sim ? `${sim.tax_regime_label} ${sim.tax_rate_pct}%` : '—'}
            betas={betasData}
          />
        ))}
      </div>
    </div>
  )
}

function BetaCard({ label, b }: { label: string; b: BetaPoint }) {
  const tone =
    b.confidence === 'high' ? 'border-emerald-200 bg-emerald-50/40 text-emerald-900'
    : b.confidence === 'medium' ? 'border-amber-200 bg-amber-50/40 text-amber-900'
    : 'border-slate-200 bg-slate-50 text-slate-700'
  return (
    <div className={cn('rounded-md border p-2.5', tone)} title={b.note}>
      <div className="text-[10px] uppercase tracking-wider opacity-70">{label}</div>
      <div className="font-bold text-sm tabular-nums mt-0.5">
        {b.beta != null ? (b.beta > 0 ? `+${b.beta.toFixed(3)}` : b.beta.toFixed(3)) : '—'}
      </div>
      <div className="text-[10px] opacity-80">
        n={b.n} · R²={b.r2 != null ? b.r2.toFixed(2) : 'n/a'} · {b.confidence}
      </div>
    </div>
  )
}

function ScenarioColumn({
  title, result, isBase = false, scenario, onChange, base, taxLabel, betas,
}: {
  title: string
  result?: ScenarioResult
  isBase?: boolean
  scenario?: Scenario
  onChange?: (next: Scenario) => void
  base?: ScenarioResult
  taxLabel: string
  betas?: BetasResp
}) {
  const sliderRow = (label: string, value: number, set: (v: number) => void,
                     min: number, max: number, step: number, suffix: string, hint?: string) => (
    <div>
      <div className="flex justify-between items-baseline text-[11px]">
        <span className="text-fg-muted">{label}</span>
        <span className="font-semibold tabular-nums">{value > 0 ? '+' : ''}{value}{suffix}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
             onChange={(e) => set(parseFloat(e.target.value))}
             className="w-full h-1 accent-purple-600" />
      {hint && <p className="text-[10px] text-fg-subtle">{hint}</p>}
    </div>
  )

  const profitColor = result && result.net_profit < 0 ? 'text-rose-700' : 'text-emerald-700'

  return (
    <Card className={cn('p-4', isBase && 'bg-bg-subtle/40')}>
      <h3 className="text-sm font-semibold text-fg mb-3">{title}</h3>

      {!isBase && scenario && onChange && betas && (
        <div className="space-y-3 mb-4 pb-4 border-b border-border-subtle">
          {sliderRow('Реклама ₽', scenario.ad_spend_pct,
                     (v) => onChange({ ...scenario, ad_spend_pct: v }),
                     -100, 300, 5, '%')}
          {sliderRow('Цена продавца', scenario.seller_price_pct,
                     (v) => onChange({ ...scenario, seller_price_pct: v }),
                     -30, 20, 1, '%',
                     scenario.seller_price_pct !== 0 && betas.betas.price.seller_price_to_orders.confidence === 'low'
                       ? `⚠ β цены на твоих данных не определима (R²=${betas.betas.price.seller_price_to_orders.r2}). Включи гипотезу ниже.`
                       : undefined)}
          {scenario.seller_price_pct !== 0 && (
            <div>
              <label className="flex items-center gap-1.5 text-[11px] text-fg-muted">
                <input type="checkbox"
                       checked={scenario.override_beta_price !== null}
                       onChange={(e) => onChange({ ...scenario,
                         override_beta_price: e.target.checked ? -1.0 : null })} />
                Включить гипотезу «цена влияет на спрос»
              </label>
              {scenario.override_beta_price !== null && (
                sliderRow('  β гипотеза', scenario.override_beta_price,
                          (v) => onChange({ ...scenario, override_beta_price: v }),
                          -2.5, 0, 0.1, '',
                          '−1.0 = классическая, −2.0 = эластичный спрос')
              )}
            </div>
          )}
          {sliderRow('Трафик (доп. показы)', scenario.impressions_pct,
                     (v) => onChange({ ...scenario, impressions_pct: v }),
                     -30, 200, 5, '%')}
          {sliderRow('Конверсия корзина→заказ', scenario.cr_cart_to_order_pct,
                     (v) => onChange({ ...scenario, cr_cart_to_order_pct: v }),
                     -20, 50, 1, '%')}
          {sliderRow('Себестоимость', scenario.cost_pct,
                     (v) => onChange({ ...scenario, cost_pct: v }),
                     -30, 30, 1, '%')}

          {/* СПП — отдельный рычаг от цены продавца */}
          <div>
            <label className="flex items-center gap-1.5 text-[11px] text-fg-muted">
              <input type="checkbox"
                     checked={scenario.spp_pct !== null}
                     onChange={(e) => {
                       const factSpp = betas && betas.base.avg_seller_price && betas.base.avg_customer_price
                         ? Math.round((1 - betas.base.avg_customer_price / betas.base.avg_seller_price) * 1000) / 10
                         : 0
                       onChange({ ...scenario, spp_pct: e.target.checked ? factSpp : null })
                     }} />
              Включить гипотезу по СПП
              {betas?.base.avg_seller_price && betas?.base.avg_customer_price && (
                <span className="text-fg-subtle ml-1">
                  (факт: {((1 - betas.base.avg_customer_price / betas.base.avg_seller_price) * 100).toFixed(1)}%)
                </span>
              )}
            </label>
            {scenario.spp_pct !== null && (
              <>
                {sliderRow('  СПП %', scenario.spp_pct,
                           (v) => onChange({ ...scenario, spp_pct: v }),
                           0, 60, 1, '%',
                           betas?.betas.price.customer_price_to_orders.confidence === 'low'
                             ? `β customer-цены на твоих данных слабая (R²=${betas.betas.price.customer_price_to_orders.r2}). Эффект на спрос будет мал.`
                             : undefined)}
                <label className="flex items-center gap-1.5 text-[10px] text-fg-muted mt-1">
                  <input type="checkbox"
                         checked={scenario.override_beta_customer_price !== null}
                         onChange={(e) => onChange({ ...scenario,
                           override_beta_customer_price: e.target.checked ? -1.5 : null })} />
                  Своя β для customer-цены
                </label>
                {scenario.override_beta_customer_price !== null && (
                  sliderRow('    β customer', scenario.override_beta_customer_price,
                            (v) => onChange({ ...scenario, override_beta_customer_price: v }),
                            -3, 0, 0.1, '',
                            'Обычно отрицательное: цена выше → меньше заказов')
                )}
              </>
            )}
          </div>
        </div>
      )}

      {result ? (
        <div className="space-y-2 text-xs">
          <RowMetric label="Показы" value={formatNumber(result.impressions)} />
          <RowMetric label="Карточка → корзина → заказ" value={`${formatNumber(result.card_visits)} → ${formatNumber(result.to_cart)} → ${formatNumber(result.orders)}`} />
          <RowMetric label="Выкуплено" value={formatNumber(result.delivered)} />
          <RowMetric label="Цена / DRR" value={`${formatCurrency(result.seller_price)} / ${result.drr_pct != null ? result.drr_pct + '%' : '—'}`} />
          <RowMetric label="Выручка" value={formatCurrency(result.revenue)} bold />
          <RowMetric label="Реклама" value={`−${formatCurrency(result.ad_spend)}`} dim />
          <RowMetric label="Все вычеты + налог" value={`−${formatCurrency(result.revenue - result.net_profit)}`} dim />
          <div className="pt-2 mt-1 border-t border-border-subtle">
            <div className="flex justify-between items-baseline">
              <span className="text-fg-muted">Чистая прибыль ({taxLabel})</span>
              <span className={cn('text-lg font-bold tabular-nums', profitColor)}>
                {formatCurrency(result.net_profit)}
              </span>
            </div>
            {result.net_margin_pct != null && (
              <div className="text-[11px] text-fg-subtle text-right">маржа {result.net_margin_pct.toFixed(1)}%</div>
            )}
            {!isBase && base && (
              <div className={cn('text-[11px] text-right mt-1',
                result.delta_net_vs_base >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
                {result.delta_net_vs_base >= 0 ? '+' : ''}{formatCurrency(result.delta_net_vs_base)} к текущему
              </div>
            )}
          </div>
          {result.drivers_explanation && result.drivers_explanation.length > 0 && (
            <div className="mt-2 p-2 rounded bg-bg-subtle/60 text-[10px] text-fg-muted space-y-0.5">
              <div className="font-semibold">Что меняется:</div>
              {result.drivers_explanation.map((e, i) => <div key={i}>• {e}</div>)}
            </div>
          )}
        </div>
      ) : (
        <div className="py-6 text-center text-fg-muted text-xs"><Loader2 className="w-4 h-4 animate-spin inline" /></div>
      )}
    </Card>
  )
}

function RowMetric({ label, value, bold = false, dim = false }: {
  label: string; value: string; bold?: boolean; dim?: boolean
}) {
  return (
    <div className="flex justify-between items-baseline">
      <span className="text-fg-muted">{label}</span>
      <span className={cn('tabular-nums', bold && 'font-bold text-emerald-700', dim && 'text-rose-700/70')}>
        {value}
      </span>
    </div>
  )
}


// === Inline product picker (empty state) ===
function WhatIfProductPicker() {
  const { setSelectedProduct } = useProductFilter()
  const [search, setSearch] = useState('')
  const { data: products = [] } = useQuery<Array<{ id: string; name: string; offer_id: string; ozon_sku: number }>>({
    queryKey: ['products-min-for-whatif'],
    queryFn: async () => (await api.get('/products/?limit=500')).data?.items || (await api.get('/products/?limit=500')).data || [],
    staleTime: 5 * 60_000,
  })

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim()
    if (!q) return products.slice(0, 50)
    return products.filter((p) =>
      p.name?.toLowerCase().includes(q) ||
      p.offer_id?.toLowerCase().includes(q) ||
      String(p.ozon_sku).includes(q)
    ).slice(0, 50)
  }, [products, search])

  return (
    <Card className="p-6 max-w-3xl mx-auto">
      <div className="text-center mb-4">
        <Sliders className="w-12 h-12 mx-auto text-purple-500 mb-3" />
        <h2 className="text-lg font-semibold text-fg">Симулятор «Что если»</h2>
        <p className="text-sm text-fg-muted mt-2 max-w-md mx-auto">
          Выбери товар — симулятор посчитает эластичности из ТВОИХ данных
          и даст играть с ценой / рекламой / конверсией.
        </p>
      </div>

      <div className="mt-4">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          autoFocus
          placeholder="Поиск товара по имени, offer_id или sku…"
          className="w-full px-3 py-2 border border-border-subtle rounded-lg text-sm bg-bg focus:border-purple-500 focus:outline-none"
        />
      </div>

      <div className="mt-3 max-h-[60vh] overflow-y-auto border border-border-subtle rounded-lg divide-y divide-border-subtle/40">
        {filtered.length === 0 && (
          <div className="p-6 text-center text-sm text-fg-muted">
            {products.length === 0 ? 'Товаров пока нет.' : 'Ничего не найдено.'}
          </div>
        )}
        {filtered.map((p) => (
          <button
            key={p.id}
            onClick={() => setSelectedProduct(p.id, p.name)}
            className="w-full px-3 py-2 text-left text-sm hover:bg-purple-50 transition-colors"
          >
            <div className="font-medium text-fg truncate">{p.name}</div>
            <div className="text-[11px] text-fg-muted">{p.offer_id} · SKU {p.ozon_sku}</div>
          </button>
        ))}
      </div>
    </Card>
  )
}
