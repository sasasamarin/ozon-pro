import { useState, useMemo, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import {
  TrendingUp, ShoppingBag, Wallet, Package,
  ArrowUpRight, ArrowDownRight, Sparkles, MapPin,
  Image as ImageIcon, Loader2, Calendar,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { CostWarningBanner } from '@/components/ui/CostWarningBanner'
import { Sparkline } from '@/components/ui/Sparkline'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'

interface KPI {
  // «Заказано» (как в кабинете Ozon)
  ordered_revenue: number
  ordered_count: number
  ordered_change_pct: number | null
  // «Продажи / Доставлено» (то что было revenue)
  revenue: number
  revenue_change_pct: number | null
  delivered_count: number
  // Разбивка
  in_transit_revenue: number
  cancelled_revenue: number
  cancelled_count: number
  gross_profit: number
  gross_profit_change_pct: number | null
  net_profit: number
  net_profit_change_pct: number | null
  tax_amount: number
  tax_regime_label: string
  tax_rate_pct: number
  orders_count: number
  orders_change_pct: number | null
  aov: number
  aov_change_pct: number | null
  ozon_expenses: number
  expense_share_pct: number | null
  sparkline: number[]
}

interface TimePoint {
  bucket: string
  revenue: number
  expenses: number
  cogs: number
  profit: number
  orders: number
}

interface ExpenseSegment {
  category: string
  amount: number
  pct: number
  op_type_filter: string | null
}

interface TopProduct {
  product_id: string
  name: string
  offer_id: string
  image_url: string | null
  revenue: number
  orders: number
  units: number
  margin: number | null
  margin_pct: number | null
}

interface ClusterSegment {
  cluster: string
  revenue: number
  orders: number
  pct: number
}

interface DashboardV2 {
  period_from: string
  period_to: string
  granularity: string
  compare: string
  has_missing_costs: boolean
  missing_costs_count: number
  kpi: KPI
  series: TimePoint[]
  expense_breakdown: ExpenseSegment[]
  top_products: TopProduct[]
  clusters: ClusterSegment[]
}

const DONUT_COLORS = [
  'fill-rose-500', 'fill-amber-500', 'fill-emerald-500',
  'fill-blue-500', 'fill-violet-500', 'fill-indigo-500',
  'fill-pink-500', 'fill-orange-500', 'fill-teal-500',
]

const PRESETS: Array<{ key: string; label: string; days: number }> = [
  { key: '7', label: '7 дней', days: 7 },
  { key: '28', label: '28 дней', days: 28 },  // окно Ozon для сверки
  { key: '30', label: '30 дней', days: 30 },
  { key: '90', label: '90 дней', days: 90 },
  { key: '365', label: 'Год', days: 365 },
  { key: '730', label: '17 месяцев', days: 514 },
]

export function Dashboard() {
  const { selectedCabinetIds, setSelectedCabinetIds } = useCabinetStore()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()

  // URL state
  const days = parseInt(params.get('days') || '30', 10)
  const granularity = (params.get('g') || 'day') as 'day' | 'week' | 'month'
  const compare = (params.get('cmp') || 'prev_period') as 'none' | 'prev_period' | 'year_ago'
  const dateFrom = params.get('from') || ''
  const dateTo = params.get('to') || ''
  const [customRange, setCustomRange] = useState(Boolean(dateFrom || dateTo))

  // Сохранение выбранных кабинетов в URL
  useEffect(() => {
    const cab = params.get('cab')
    if (cab && cab !== selectedCabinetIds.join(',')) {
      setSelectedCabinetIds(cab.split(',').filter(Boolean))
    }
  }, [])

  const updateParam = (k: string, v: string | undefined) => {
    const p = new URLSearchParams(params)
    if (v) p.set(k, v); else p.delete(k)
    setParams(p, { replace: true })
  }

  const { data, isLoading } = useQuery<DashboardV2>({
    queryKey: ['dashboard-v2', selectedCabinetIds, days, granularity, compare, dateFrom, dateTo],
    queryFn: async () => {
      const p = new URLSearchParams({ granularity, compare })
      if (dateFrom) p.append('date_from', dateFrom)
      if (dateTo) p.append('date_to', dateTo)
      if (!dateFrom && !dateTo) p.append('days', String(days))
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      const res = await api.get(`/dashboard/v2/?${p.toString()}`)
      return res.data
    },
  })

  const kpi = data?.kpi
  const series = data?.series || []
  const maxRev = Math.max(1, ...series.map((s) => s.revenue))

  return (
    <div className="relative">
      <div className="relative flex flex-col gap-5">
        {/* === HEADER === */}
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-border-subtle bg-bg-subtle/60 px-2.5 py-1 text-xs font-medium text-fg-muted">
              <Sparkles className="w-3 h-3" />
              {data?.period_from} … {data?.period_to}
            </div>
            <h1 className="text-3xl font-semibold text-fg tracking-tight mt-3">Дашборд</h1>
          </div>
        </div>

        {/* === TOOLBAR === */}
        <Card className="p-3 flex flex-wrap items-center gap-2">
          {PRESETS.map((p) => (
            <button
              key={p.key}
              onClick={() => {
                setCustomRange(false)
                updateParam('from', undefined)
                updateParam('to', undefined)
                updateParam('days', p.key)
              }}
              className={cn(
                'px-3 py-1.5 rounded-md text-xs border transition-colors',
                String(days) === p.key && !customRange
                  ? 'border-fg bg-fg text-bg'
                  : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
              )}
            >
              {p.label}
            </button>
          ))}
          <button
            onClick={() => setCustomRange((v) => !v)}
            className={cn(
              'px-3 py-1.5 rounded-md text-xs border transition-colors inline-flex items-center gap-1',
              customRange
                ? 'border-fg bg-fg text-bg'
                : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
            )}
          >
            <Calendar className="w-3 h-3" /> Произвольно
          </button>

          {customRange && (
            <>
              <Input type="date" value={dateFrom}
                onChange={(e) => updateParam('from', e.target.value)} className="h-8 w-[140px] text-xs" />
              <Input type="date" value={dateTo}
                onChange={(e) => updateParam('to', e.target.value)} className="h-8 w-[140px] text-xs" />
            </>
          )}

          <div className="w-px h-5 bg-border-subtle mx-2" />

          <span className="text-xs text-fg-muted">Гранулярность:</span>
          {(['day', 'week', 'month'] as const).map((g) => (
            <button key={g} onClick={() => updateParam('g', g)} className={cn(
              'px-2 py-1 rounded text-xs border',
              granularity === g ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle',
            )}>
              {g === 'day' ? 'День' : g === 'week' ? 'Неделя' : 'Месяц'}
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

        {data?.has_missing_costs && (
          <CostWarningBanner count={data.missing_costs_count} context="profit" />
        )}

        {/* === KPI ROW === */}
        {isLoading ? (
          <Card className="py-16 flex justify-center text-fg-muted">
            <Loader2 className="w-5 h-5 animate-spin" />
          </Card>
        ) : (
          <>
            {/* ВЕРХНЯЯ ПОЛОСА: «Заказано» (как в кабинете Ozon) — для сверки */}
            <Card className="p-4">
              <div className="flex items-start justify-between flex-wrap gap-3">
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-fg-muted">
                    Заказано (как в кабинете Ozon)
                  </div>
                  <div className="flex items-baseline gap-3 mt-1 flex-wrap">
                    <span className="text-2xl font-bold text-fg tabular-nums">
                      {formatCurrency(kpi?.ordered_revenue ?? 0)}
                    </span>
                    <span className="text-sm text-fg-muted tabular-nums">
                      {formatNumber(kpi?.ordered_count ?? 0)} заказов
                    </span>
                    {kpi?.ordered_change_pct != null && (
                      <span className={cn('text-xs tabular-nums',
                        kpi.ordered_change_pct >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
                        {kpi.ordered_change_pct >= 0 ? '+' : ''}{kpi.ordered_change_pct.toFixed(1)}%
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-fg-muted mt-1">
                    Все заказы периода (вкл. в пути и отменённые). Совпадает с Ozon admin → «Заказано на сумму».
                  </p>
                </div>
                <div className="flex gap-4 text-xs flex-wrap">
                  <div>
                    <div className="text-fg-muted text-[10px] uppercase">В пути</div>
                    <div className="font-semibold tabular-nums text-amber-700">
                      {formatCurrency(kpi?.in_transit_revenue ?? 0)}
                    </div>
                  </div>
                  <div>
                    <div className="text-fg-muted text-[10px] uppercase">Отменено</div>
                    <div className="font-semibold tabular-nums text-rose-700">
                      {formatCurrency(kpi?.cancelled_revenue ?? 0)}
                    </div>
                    <div className="text-fg-muted text-[10px] tabular-nums">
                      {kpi?.cancelled_count ?? 0} шт
                    </div>
                  </div>
                </div>
              </div>
            </Card>

            {/* ОСНОВНЫЕ KPI: фактические продажи + прибыль */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
              <KpiCard
                label="Продажи (доставлено)"
                value={formatCurrency(kpi?.revenue ?? 0)}
                change={kpi?.revenue_change_pct}
                subtitle={kpi?.delivered_count ? `${formatNumber(kpi.delivered_count)} выкуплено` : undefined}
                spark={kpi?.sparkline || []}
                icon={TrendingUp}
                iconBg="from-emerald-50 to-white text-emerald-600"
                clickTo={`/finance/transactions?date_from=${data?.period_from || ''}&date_to=${data?.period_to || ''}`}
              />
              <KpiCard
                label="Прибыль (до налога)"
                value={formatCurrency(kpi?.gross_profit ?? 0)}
                change={kpi?.gross_profit_change_pct}
                spark={kpi?.sparkline || []}
                icon={Package}
                iconBg="from-indigo-50 to-white text-indigo-600"
                subtitle="выручка − себест − комиссия"
                clickTo="/finance/pnl"
              />
              <KpiCard
                label={`Чистая (${kpi?.tax_regime_label ?? 'УСН'} ${kpi?.tax_rate_pct ?? 6}%)`}
                value={formatCurrency(kpi?.net_profit ?? 0)}
                change={kpi?.net_profit_change_pct}
                spark={kpi?.sparkline || []}
                icon={Wallet}
                iconBg="from-emerald-50 to-white text-emerald-700"
                subtitle={kpi?.tax_amount ? `− налог ${formatCurrency(kpi.tax_amount)}` : undefined}
                clickTo="/finance/pnl"
              />
              <KpiCard
                label="Заказы (доставлено)"
                value={formatNumber(kpi?.orders_count ?? 0)}
                change={kpi?.orders_change_pct}
                spark={kpi?.sparkline || []}
                icon={ShoppingBag}
                iconBg="from-amber-50 to-white text-amber-700"
                clickTo={`/orders?date_from=${data?.period_from || ''}&date_to=${data?.period_to || ''}`}
              />
              <KpiCard
                label="Средний чек"
                value={formatCurrency(kpi?.aov ?? 0)}
                change={kpi?.aov_change_pct}
                spark={[]}
                icon={Wallet}
                iconBg="from-violet-50 to-white text-violet-600"
              />
              <KpiCard
                label="Расходы Ozon"
                value={formatCurrency(kpi?.ozon_expenses ?? 0)}
                change={null}
                subtitle={kpi?.expense_share_pct != null ? `${kpi.expense_share_pct}% от продаж` : undefined}
                spark={[]}
                icon={Wallet}
                iconBg="from-rose-50 to-white text-rose-600"
                clickTo="/finance/transactions"
              />
            </div>
          </>
        )}

        {/* === MAIN CHART === */}
        <Card className="p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-base font-semibold text-fg">Динамика</h2>
            <p className="text-xs text-fg-muted">
              {series.length} точек · кликни на bar чтобы увидеть детали дня
            </p>
          </div>

          {series.length === 0 ? (
            <p className="text-sm text-fg-muted text-center py-8">Нет данных за период</p>
          ) : (
            <div className="overflow-x-auto pb-2">
              <div className="flex items-end gap-1 min-w-[600px] h-[180px]">
                {series.map((s) => {
                  const h = Math.max(2, (s.revenue / maxRev) * 160)
                  const profitH = Math.max(2, (Math.max(0, s.profit) / maxRev) * 160)
                  return (
                    <button
                      key={s.bucket}
                      onClick={() => navigate(`/orders?date_from=${s.bucket}&date_to=${s.bucket}`)}
                      className="flex-1 min-w-[8px] flex flex-col items-center gap-1 group"
                      title={`${s.bucket}: выручка ${formatCurrency(s.revenue)}, прибыль ${formatCurrency(s.profit)}, ${s.orders} заказов`}
                    >
                      <div className="relative w-full flex flex-col items-center justify-end" style={{ height: 160 }}>
                        <div
                          className="w-full bg-emerald-300 group-hover:bg-emerald-500 transition-colors rounded-t-sm"
                          style={{ height: h }}
                        />
                        <div
                          className="absolute bottom-0 w-full bg-indigo-400 group-hover:bg-indigo-600 transition-colors rounded-t-sm"
                          style={{ height: profitH, width: '50%' }}
                        />
                      </div>
                      <span className="text-[9px] text-fg-subtle opacity-0 group-hover:opacity-100 whitespace-nowrap tabular-nums">
                        {new Date(s.bucket).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })}
                      </span>
                    </button>
                  )
                })}
              </div>
              <div className="flex items-center gap-4 mt-3 text-xs text-fg-muted">
                <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 bg-emerald-300 rounded" /> Выручка</span>
                <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 bg-indigo-400 rounded" /> Прибыль</span>
              </div>
            </div>
          )}
        </Card>

        {/* === 3 WIDGETS === */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Expense donut */}
          <Card className="p-5">
            <h2 className="text-base font-semibold text-fg">Расходы Ozon</h2>
            <p className="text-xs text-fg-muted mt-0.5">кликай по категории → /finance/transactions</p>
            <div className="mt-4 flex flex-col gap-2">
              {(data?.expense_breakdown || []).slice(0, 8).map((e, idx) => (
                <button
                  key={e.category}
                  onClick={() => {
                    const q = new URLSearchParams()
                    if (e.op_type_filter) q.set('operation_type', e.op_type_filter)
                    navigate(`/finance/transactions?${q.toString()}`)
                  }}
                  className="flex items-center gap-2 text-left hover:bg-bg-subtle/50 rounded px-1.5 py-1 -mx-1.5"
                >
                  <span className={cn('w-2.5 h-2.5 rounded-sm shrink-0', DONUT_COLORS[idx]?.replace('fill-', 'bg-'))} />
                  <span className="text-xs text-fg-muted flex-1 truncate">{e.category}</span>
                  <span className="text-xs tabular-nums text-fg">{formatCurrency(e.amount)}</span>
                  <span className="text-[10px] tabular-nums text-fg-subtle w-10 text-right">{e.pct}%</span>
                </button>
              ))}
              {(data?.expense_breakdown || []).length === 0 && (
                <p className="text-sm text-fg-muted text-center py-4">Нет расходов</p>
              )}
            </div>
          </Card>

          {/* Top products */}
          <Card className="p-5">
            <h2 className="text-base font-semibold text-fg">Топ-10 товаров</h2>
            <p className="text-xs text-fg-muted mt-0.5">кликай → карточка товара</p>
            <div className="mt-4 flex flex-col gap-2">
              {(data?.top_products || []).slice(0, 10).map((p, idx) => (
                <Link
                  key={p.product_id}
                  to={`/products/${p.product_id}`}
                  className="flex items-center gap-2 hover:bg-bg-subtle/50 rounded -mx-1.5 px-1.5 py-1"
                >
                  <span className="w-4 text-[10px] font-mono text-fg-subtle">{idx + 1}.</span>
                  {p.image_url ? (
                    <img src={p.image_url} alt="" className="w-7 h-7 rounded object-cover shrink-0 border border-border-subtle" />
                  ) : (
                    <div className="w-7 h-7 rounded bg-bg-subtle flex items-center justify-center shrink-0">
                      <ImageIcon className="w-3 h-3 text-fg-subtle" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium text-fg truncate">{p.name}</div>
                    <div className="text-[10px] text-fg-subtle">{p.orders} зак · {p.units} шт{p.margin_pct != null ? ` · ${p.margin_pct}% маржа` : ''}</div>
                  </div>
                  <span className="text-xs font-mono tabular-nums text-fg shrink-0">
                    {formatCurrency(p.revenue)}
                  </span>
                </Link>
              ))}
            </div>
          </Card>

          {/* Clusters */}
          <Card className="p-5">
            <h2 className="text-base font-semibold text-fg flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5 text-fg-muted" />
              По кластерам
            </h2>
            <p className="text-xs text-fg-muted mt-0.5">откуда отгружают</p>
            <div className="mt-4 flex flex-col gap-1.5">
              {(data?.clusters || []).slice(0, 12).map((c, idx) => (
                <div key={c.cluster} className="flex items-center gap-2 text-xs">
                  <span className="text-fg-muted truncate flex-1" title={c.cluster}>
                    {c.cluster.length > 22 ? c.cluster.substring(0, 22) + '…' : c.cluster}
                  </span>
                  <div className="w-12 h-1.5 bg-bg-subtle rounded-full overflow-hidden">
                    <div className={cn('h-full rounded-full', DONUT_COLORS[idx % DONUT_COLORS.length]?.replace('fill-', 'bg-'))}
                      style={{ width: `${Math.min(100, c.pct * 2)}%` }} />
                  </div>
                  <span className="text-fg tabular-nums w-10 text-right">{c.pct}%</span>
                </div>
              ))}
              {(data?.clusters || []).length === 0 && (
                <p className="text-fg-muted text-center py-4">Нет данных</p>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}

interface KpiCardProps {
  label: string
  value: string
  change: number | null | undefined
  spark: number[]
  icon: React.ComponentType<{ className?: string }>
  iconBg: string
  subtitle?: string
  clickTo?: string
}

function KpiCard({ label, value, change, spark, icon: Icon, iconBg, subtitle, clickTo }: KpiCardProps) {
  const navigate = useNavigate()
  const body = (
    <>
      <div className="flex items-center justify-between mb-3">
        <div className={cn('w-8 h-8 rounded-lg bg-gradient-to-br border border-white shadow-sm flex items-center justify-center', iconBg)}>
          <Icon className="w-4 h-4" />
        </div>
        {change != null && (
          <span className={cn(
            'inline-flex items-center gap-0.5 text-[10px] font-semibold px-1.5 py-0.5 rounded-full tabular-nums',
            change >= 0 ? 'text-emerald-700 bg-emerald-50' : 'text-rose-700 bg-rose-50',
          )}>
            {change >= 0 ? <ArrowUpRight className="w-2.5 h-2.5" /> : <ArrowDownRight className="w-2.5 h-2.5" />}
            {change >= 0 ? '+' : ''}{change}%
          </span>
        )}
      </div>
      <p className="text-[10px] font-medium text-fg-muted uppercase tracking-wider">{label}</p>
      <p className="text-[22px] leading-tight font-semibold text-fg mt-0.5 tabular-nums">{value}</p>
      {subtitle && <p className="text-[10px] text-fg-muted mt-0.5">{subtitle}</p>}
      {spark.length > 0 && (
        <div className="mt-2 -mx-1 text-emerald-500">
          <Sparkline points={spark} />
        </div>
      )}
    </>
  )
  if (clickTo) {
    return (
      <Card
        onClick={() => navigate(clickTo)}
        className="p-3 cursor-pointer hover:shadow-elev hover:border-border transition-all duration-200"
      >
        {body}
      </Card>
    )
  }
  return <Card className="p-3">{body}</Card>
}
