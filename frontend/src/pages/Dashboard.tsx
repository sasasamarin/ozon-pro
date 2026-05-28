import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  TrendingUp,
  ShoppingBag,
  Wallet,
  Package,
  ArrowUpRight,
  ArrowDownRight,
  Sparkles,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { CostWarningBanner } from '@/components/ui/CostWarningBanner'
import { Sparkline } from '@/components/ui/Sparkline'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'

interface KPI {
  revenue: number
  revenue_change_pct: number | null
  ozon_expenses: number
  ozon_expenses_pct_of_revenue: number | null
  gross_profit: number
  gross_profit_change_pct: number | null
  orders_count: number
  orders_change_pct: number | null
  avg_order_value: number
}

interface ExpenseRow {
  category: string
  amount: number
  pct_of_expenses: number
}

interface DailyPoint {
  date: string
  revenue: number
  expenses: number
  profit: number
}

interface TopProduct {
  product_id: string
  name: string
  offer_id: string
  revenue: number
  units: number
  share_pct: number
}

interface DashboardData {
  period_from: string
  period_to: string
  cabinet_ids: string[]
  has_missing_costs: boolean
  missing_costs_count: number
  kpi: KPI
  expense_breakdown: ExpenseRow[]
  daily_series: DailyPoint[]
  top_products: TopProduct[]
}

export function Dashboard() {
  const { selectedCabinetIds } = useCabinetStore()

  const { data, isLoading } = useQuery<DashboardData>({
    queryKey: ['dashboard', selectedCabinetIds, 30],
    queryFn: async () => {
      const params = new URLSearchParams({ days: '30' })
      selectedCabinetIds.forEach((id) => params.append('cabinet_ids', id))
      const res = await api.get(`/dashboard/?${params.toString()}`)
      return res.data
    },
  })

  const kpi = data?.kpi
  const revSeries = (data?.daily_series || []).map((d) => d.revenue)
  const profitSeries = (data?.daily_series || []).map((d) => d.profit)
  const expensesSeries = (data?.daily_series || []).map((d) => d.expenses)

  return (
    <div className="relative">
      <div
        aria-hidden
        className="absolute -top-20 -right-20 w-[520px] h-[520px] rounded-full bg-aurora-soft blur-3xl pointer-events-none -z-0"
      />

      <div className="relative flex flex-col gap-6">
        {/* Header */}
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-border-subtle bg-bg-subtle/60 backdrop-blur-sm px-2.5 py-1 text-xs font-medium text-fg-muted">
            <Sparkles className="w-3 h-3" />
            Сводка · 30 дней
          </div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight mt-3">Дашборд</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Выручка, расходы Ozon и прибыль по выбранным кабинетам.
          </p>
        </div>

        {/* Cost warning */}
        {data?.has_missing_costs && (
          <CostWarningBanner count={data.missing_costs_count} context="profit" />
        )}

        {/* KPI cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard
            label="Выручка"
            value={kpi?.revenue ?? 0}
            change={kpi?.revenue_change_pct ?? null}
            icon={TrendingUp}
            iconColor="text-emerald-600"
            iconBg="from-emerald-50 to-white"
            sparkPoints={revSeries}
            sparkColor="text-emerald-500"
            formatter={formatCurrency}
            isLoading={isLoading}
          />
          <KpiCard
            label="Расходы Ozon"
            value={kpi?.ozon_expenses ?? 0}
            change={null}
            subtitle={
              kpi?.ozon_expenses_pct_of_revenue != null
                ? `${kpi.ozon_expenses_pct_of_revenue}% от выручки`
                : null
            }
            icon={Wallet}
            iconColor="text-rose-600"
            iconBg="from-rose-50 to-white"
            sparkPoints={expensesSeries}
            sparkColor="text-rose-500"
            formatter={formatCurrency}
            isLoading={isLoading}
          />
          <KpiCard
            label="Валовая прибыль"
            value={kpi?.gross_profit ?? 0}
            change={kpi?.gross_profit_change_pct ?? null}
            subtitle="выручка − себестоимость − Ozon"
            icon={Package}
            iconColor="text-indigo-600"
            iconBg="from-indigo-50 to-white"
            sparkPoints={profitSeries}
            sparkColor="text-indigo-500"
            formatter={formatCurrency}
            isLoading={isLoading}
          />
          <KpiCard
            label="Заказы"
            value={kpi?.orders_count ?? 0}
            change={kpi?.orders_change_pct ?? null}
            subtitle={kpi ? `средний чек ${formatCurrency(kpi.avg_order_value)}` : null}
            icon={ShoppingBag}
            iconColor="text-amber-700"
            iconBg="from-amber-50 to-white"
            sparkPoints={revSeries}
            sparkColor="text-amber-600"
            formatter={formatNumber}
            isLoading={isLoading}
          />
        </div>

        {/* Daily chart + top products */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card className="lg:col-span-2 p-6">
            <h2 className="text-base font-semibold text-fg">Динамика по дням</h2>
            <p className="text-xs text-fg-muted mt-0.5">
              Выручка (зелёный) · Расходы (красный) · Прибыль (фиолетовый)
            </p>
            <div className="mt-5 flex flex-col gap-2">
              <ChartRow label="Выручка" series={revSeries} color="text-emerald-500" />
              <ChartRow label="Расходы" series={expensesSeries} color="text-rose-500" />
              <ChartRow label="Прибыль" series={profitSeries} color="text-indigo-500" />
            </div>
            <div className="mt-4 flex justify-between text-xs text-fg-subtle font-mono">
              <span>{data?.period_from}</span>
              <span>{data?.period_to}</span>
            </div>
          </Card>

          <Card className="p-6">
            <h2 className="text-base font-semibold text-fg">Топ товаров</h2>
            <p className="text-xs text-fg-muted mt-0.5">по выручке за 30 дней</p>
            <div className="mt-4 flex flex-col gap-3">
              {(data?.top_products || []).map((p, idx) => (
                <Link
                  to={`/products`}
                  key={p.product_id}
                  className="flex items-center gap-3 -mx-2 px-2 py-1.5 rounded-md hover:bg-bg-subtle transition-colors"
                >
                  <span className="w-5 text-xs font-mono text-fg-subtle tabular-nums">
                    {idx + 1}.
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-fg truncate">{p.name}</p>
                    <p className="text-xs text-fg-muted">
                      {formatNumber(p.units)} шт · {p.share_pct}%
                    </p>
                  </div>
                  <span className="text-sm font-semibold text-fg tabular-nums shrink-0">
                    {formatCurrency(p.revenue)}
                  </span>
                </Link>
              ))}
              {!isLoading && (data?.top_products || []).length === 0 && (
                <p className="text-sm text-fg-muted text-center py-6">Нет данных за период</p>
              )}
            </div>
          </Card>
        </div>

        {/* Expense breakdown */}
        <Card className="p-6">
          <h2 className="text-base font-semibold text-fg">Структура расходов Ozon</h2>
          <p className="text-xs text-fg-muted mt-0.5">из транзакций за 30 дней</p>
          <div className="mt-4 flex flex-col gap-2">
            {(data?.expense_breakdown || []).map((row) => (
              <div key={row.category} className="flex items-center gap-3">
                <span className="w-44 text-sm text-fg-muted shrink-0">{row.category}</span>
                <div className="flex-1 h-2 bg-bg-subtle rounded-full overflow-hidden">
                  <div
                    className="h-full bg-rose-400 rounded-full"
                    style={{ width: `${Math.min(100, row.pct_of_expenses)}%` }}
                  />
                </div>
                <span className="text-sm font-semibold text-fg tabular-nums w-28 text-right shrink-0">
                  {formatCurrency(row.amount)}
                </span>
                <span className="text-xs text-fg-muted tabular-nums w-12 text-right shrink-0">
                  {row.pct_of_expenses}%
                </span>
              </div>
            ))}
            {!isLoading && (data?.expense_breakdown || []).length === 0 && (
              <p className="text-sm text-fg-muted text-center py-6">Нет расходов за период</p>
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}

interface KpiCardProps {
  label: string
  value: number
  change: number | null
  subtitle?: string | null
  icon: React.ComponentType<{ className?: string }>
  iconColor: string
  iconBg: string
  sparkPoints: number[]
  sparkColor: string
  formatter: (v: number) => string
  isLoading: boolean
}

function KpiCard({
  label,
  value,
  change,
  subtitle,
  icon: Icon,
  iconColor,
  iconBg,
  sparkPoints,
  sparkColor,
  formatter,
  isLoading,
}: KpiCardProps) {
  return (
    <Card className="p-5 hover:shadow-elev hover:border-border transition-all duration-200">
      <div className="flex items-center justify-between mb-4">
        <div
          className={cn(
            'w-9 h-9 rounded-lg bg-gradient-to-br border border-white shadow-sm flex items-center justify-center',
            iconBg
          )}
        >
          <Icon className={cn('w-4 h-4', iconColor)} />
        </div>
        {change != null && (
          <span
            className={cn(
              'inline-flex items-center gap-0.5 text-[11px] font-semibold px-2 py-0.5 rounded-full tabular-nums',
              change >= 0 ? 'text-success bg-green-50' : 'text-error bg-red-50'
            )}
          >
            {change >= 0 ? (
              <ArrowUpRight className="w-3 h-3" />
            ) : (
              <ArrowDownRight className="w-3 h-3" />
            )}
            {change >= 0 ? '+' : ''}
            {change}%
          </span>
        )}
      </div>
      <p className="text-xs font-medium text-fg-muted uppercase tracking-wider">{label}</p>
      <p className="text-[26px] leading-tight font-semibold text-fg mt-1 tabular-nums">
        {isLoading ? (
          <span className="inline-block w-24 h-7 bg-bg-subtle rounded animate-pulse" />
        ) : (
          formatter(value)
        )}
      </p>
      {subtitle && <p className="text-xs text-fg-muted mt-1">{subtitle}</p>}
      {sparkPoints.length > 0 && (
        <div className={cn('mt-3 -mx-1', sparkColor)}>
          <Sparkline points={sparkPoints} />
        </div>
      )}
    </Card>
  )
}

function ChartRow({ label, series, color }: { label: string; series: number[]; color: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-20 text-xs text-fg-muted shrink-0">{label}</span>
      <div className={cn('flex-1 -my-1', color)}>
        <Sparkline points={series.length > 0 ? series : [0]} />
      </div>
      <span className="text-sm font-semibold text-fg tabular-nums w-28 text-right shrink-0">
        {formatCurrency(series.reduce((s, v) => s + v, 0))}
      </span>
    </div>
  )
}
