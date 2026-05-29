import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { TrendingUp, ArrowUpRight, ArrowDownRight, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { CostWarningBanner } from '@/components/ui/CostWarningBanner'
import { api } from '@/lib/api'
import { formatCurrency, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'

interface PnLRow {
  label: string
  amount: number
  pct_of_revenue: number | null
  is_subtotal: boolean
  is_negative: boolean
  transactions_filter: Record<string, unknown> | null
}

interface PnLResp {
  period_from: string
  period_to: string
  has_missing_costs: boolean
  missing_costs_count: number
  revenue: number
  cogs: number
  gross_profit: number
  total_ozon_expenses: number
  marginal_profit: number
  rows: PnLRow[]
  prev_revenue: number | null
  prev_marginal_profit: number | null
}

export function FinancePnL() {
  const { selectedCabinetIds } = useCabinetStore()
  const [days, setDays] = useState(30)
  const navigate = useNavigate()

  const { data, isLoading } = useQuery<PnLResp>({
    queryKey: ['pnl', selectedCabinetIds, days],
    queryFn: async () => {
      const params = new URLSearchParams({ days: String(days), compare: 'true' })
      selectedCabinetIds.forEach((id) => params.append('cabinet_ids', id))
      const res = await api.get(`/finance/pnl/?${params.toString()}`)
      return res.data
    },
  })

  const marginPct = data ? (data.revenue > 0 ? (data.marginal_profit / data.revenue) * 100 : null) : null
  const prevMarginPct = data?.prev_revenue
    ? data.prev_marginal_profit != null && data.prev_revenue > 0
      ? (data.prev_marginal_profit / data.prev_revenue) * 100
      : null
    : null
  const marginDelta = marginPct != null && prevMarginPct != null ? marginPct - prevMarginPct : null

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">P&amp;L отчёт</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Декомпозиция выручка → расходы → маржинальная прибыль · {data?.period_from} … {data?.period_to}
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

      {data?.has_missing_costs && (
        <CostWarningBanner count={data.missing_costs_count} context="profit" />
      )}

      {/* Header KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiTile label="Выручка" value={data?.revenue ?? 0} prev={data?.prev_revenue ?? null} />
        <KpiTile label="Себестоимость" value={-(data?.cogs ?? 0)} prev={null} negative />
        <KpiTile label="Расходы Ozon" value={-(data?.total_ozon_expenses ?? 0)} prev={null} negative />
        <KpiTile
          label="Маржинальная прибыль"
          value={data?.marginal_profit ?? 0}
          prev={data?.prev_marginal_profit ?? null}
          accent
          subtitle={
            marginPct != null
              ? `маржа ${marginPct.toFixed(1)}%${marginDelta != null ? ` (${marginDelta >= 0 ? '+' : ''}${marginDelta.toFixed(1)} п.п.)` : ''}`
              : undefined
          }
        />
      </div>

      <Card className="overflow-hidden">
        <div className="px-6 py-4 border-b border-border-subtle flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-fg flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-fg-muted" />
              Декомпозиция
            </h2>
            <p className="text-xs text-fg-muted mt-0.5">кликни на расход → детальная таблица транзакций</p>
          </div>
        </div>

        {isLoading ? (
          <div className="py-16 flex justify-center items-center text-fg-muted">
            <Loader2 className="w-5 h-5 animate-spin mr-2" /> Считаем…
          </div>
        ) : (
          <div className="divide-y divide-border-subtle">
            {(data?.rows || []).map((r, idx) => {
              const clickable = r.is_negative && !r.is_subtotal
              return (
                <div
                  key={idx}
                  onClick={() => {
                    if (!clickable) return
                    // drill: переходим в /finance/transactions с фильтром по описанию
                    const cleanLabel = r.label.replace(/^−\s*/, '')
                    const params = new URLSearchParams({ search: cleanLabel })
                    navigate(`/finance/transactions?${params.toString()}`)
                  }}
                  className={cn(
                    'px-6 py-3 flex items-center justify-between text-sm',
                    r.is_subtotal && 'bg-bg-subtle/50 font-semibold text-fg border-y border-border',
                    !r.is_subtotal && 'hover:bg-bg-subtle/40',
                    clickable && 'cursor-pointer',
                  )}
                >
                  <span
                    className={cn(
                      r.is_subtotal ? 'text-fg' : r.is_negative ? 'text-fg-muted' : 'text-fg',
                    )}
                  >
                    {r.label}
                  </span>
                  <div className="flex items-baseline gap-4">
                    <span
                      className={cn(
                        'font-mono tabular-nums',
                        r.is_subtotal
                          ? r.amount >= 0
                            ? 'text-emerald-700 font-semibold text-lg'
                            : 'text-rose-700 font-semibold text-lg'
                          : r.is_negative
                          ? 'text-rose-700'
                          : 'text-fg',
                      )}
                    >
                      {formatCurrency(r.amount)}
                    </span>
                    {r.pct_of_revenue != null && (
                      <span className="text-xs text-fg-subtle tabular-nums w-16 text-right">
                        {r.pct_of_revenue.toFixed(1)}%
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
}

function KpiTile({
  label, value, prev, negative, accent, subtitle,
}: {
  label: string
  value: number
  prev: number | null
  negative?: boolean
  accent?: boolean
  subtitle?: string
}) {
  const delta = prev != null && prev !== 0 ? ((value - prev) / Math.abs(prev)) * 100 : null
  return (
    <Card className={cn('p-4', accent && 'border-2 border-indigo-200 bg-indigo-50/40')}>
      <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">{label}</p>
      <p
        className={cn(
          'text-[22px] leading-tight font-semibold mt-1 tabular-nums',
          accent ? (value >= 0 ? 'text-emerald-700' : 'text-rose-700') : negative ? 'text-rose-700' : 'text-fg',
        )}
      >
        {formatCurrency(value)}
      </p>
      {subtitle && <p className="text-xs text-fg-muted mt-1">{subtitle}</p>}
      {delta != null && !accent && (
        <p
          className={cn(
            'text-xs mt-1.5 tabular-nums inline-flex items-center gap-0.5',
            delta >= 0 ? 'text-emerald-700' : 'text-rose-700',
          )}
        >
          {delta >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
          {delta >= 0 ? '+' : ''}
          {delta.toFixed(1)}% vs прошлый
        </p>
      )}
    </Card>
  )
}
