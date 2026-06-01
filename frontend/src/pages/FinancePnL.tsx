import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, Link } from 'react-router-dom'
import { TrendingUp, ArrowUpRight, ArrowDownRight, Loader2, FileSpreadsheet, AlertTriangle } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { CostWarningBanner } from '@/components/ui/CostWarningBanner'
import { SelectedProductBanner } from '@/components/SelectedProductBanner'
import { api } from '@/lib/api'
import { formatCurrency, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'
import { XlsxCoverageMatrix } from '@/components/XlsxCoverageMatrix'

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
  seller_revenue: number       // что Ozon начислил (accruals_for_sale)
  buyer_revenue: number        // что заплатил покупатель (Order.total_amount)
  revenue: number              // = seller_revenue (legacy alias)
  returned_revenue: number
  effective_revenue: number
  cogs: number
  gross_profit: number
  total_ozon_expenses: number
  marginal_profit: number
  tax_regime: string
  tax_regime_label: string
  tax_rate_pct: number
  tax_amount: number
  vat_amount: number
  net_profit: number
  net_margin_pct: number | null
  rows: PnLRow[]
  prev_revenue: number | null
  prev_marginal_profit: number | null
  prev_net_profit: number | null
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
          {[7, 28, 30, 90, 365].map((d) => (
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

      {/* Баннер XLSX покрытия: показывает за какие месяцы есть точные числа Ozon */}
      <XlsxCoverageBanner />

      {data && (data.seller_revenue - data.buyer_revenue) > 1 && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50/60 px-4 py-3 text-sm">
          <p className="font-semibold text-emerald-900">Методика выручки исправлена</p>
          <p className="text-emerald-800 mt-1">
            Top-line теперь = <strong>Выручка продавца</strong> (Ozon начислил, accruals_for_sale).
            Включает «Баллы за скидки» и «Программы партнёров» — это деньги, которые
            Ozon доплачивает за участие в СПП. От этой цифры считается комиссия и маржа.
          </p>
          <p className="text-emerald-800 mt-1">
            За период: продавец получил <span className="font-mono font-semibold">{formatCurrency(data.seller_revenue)}</span>,
            покупатели заплатили <span className="font-mono">{formatCurrency(data.buyer_revenue)}</span>,
            Ozon доплатил <span className="font-mono font-semibold text-emerald-900">
              +{formatCurrency(data.seller_revenue - data.buyer_revenue)}
            </span>.
          </p>
        </div>
      )}
      {data && data.returned_revenue > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50/60 px-4 py-3 text-sm">
          <p className="font-semibold text-amber-900">Возвраты — отдельной строкой</p>
          <p className="text-amber-800 mt-1">
            Возвраты {formatCurrency(data.returned_revenue)} вычитаются из выручки.
            Налог считается от эффективной выручки.
          </p>
        </div>
      )}

      <SelectedProductBanner />

      {/* Header KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <KpiTile label="Выручка" value={data?.revenue ?? 0} prev={data?.prev_revenue ?? null} />
        <KpiTile label="Себестоимость" value={-(data?.cogs ?? 0)} prev={null} negative />
        <KpiTile label="Расходы Ozon" value={-(data?.total_ozon_expenses ?? 0)} prev={null} negative />
        <KpiTile
          label="Маржинальная (до налога)"
          value={data?.marginal_profit ?? 0}
          prev={data?.prev_marginal_profit ?? null}
          subtitle={
            marginPct != null
              ? `${marginPct.toFixed(1)}%${marginDelta != null ? ` (${marginDelta >= 0 ? '+' : ''}${marginDelta.toFixed(1)} п.п.)` : ''}`
              : undefined
          }
        />
        <KpiTile
          label={`Чистая (после налога${data ? ` ${data.tax_regime_label} ${data.tax_rate_pct}%` : ''})`}
          value={data?.net_profit ?? 0}
          prev={data?.prev_net_profit ?? null}
          accent
          subtitle={
            data?.net_margin_pct != null
              ? `маржа ${data.net_margin_pct.toFixed(1)}%`
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


interface UploadStatus {
  cabinet_id: string
  cabinet_name: string
  month: string
  imported_at: string
  sku_count: number
}

/**
 * Баннер «За какие месяцы загружен XLSX Ozon». Показывает покрытие точными
 * данными по кабинетам — где есть, чего ждать. Принцип «честность источников».
 */
function XlsxCoverageBanner() {
  const { data: uploads = [] } = useQuery<UploadStatus[]>({
    queryKey: ['unit-economy-status'],
    queryFn: async () => (await api.get('/finance/unit-economy/status')).data,
    staleTime: 60_000,
  })

  // Группируем по кабинету
  const byCabinet = uploads.reduce<Record<string, UploadStatus[]>>((acc, u) => {
    if (!acc[u.cabinet_name]) acc[u.cabinet_name] = []
    acc[u.cabinet_name].push(u)
    return acc
  }, {})
  const hasAny = uploads.length > 0

  if (!hasAny) {
    return (
      <Card className="p-3 bg-amber-50/60 border-amber-200/60 text-sm flex items-center gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-700 shrink-0" />
        <div className="flex-1">
          <strong className="text-amber-900">XLSX «Экономика магазина» не загружен.</strong>{' '}
          Хранение и детальная реклама в P&amp;L = оценки. Загрузи XLSX за месяц для точного зеркала Ozon.
        </div>
        <Link to="/finance/unit-economy/import"
              className="text-xs font-medium px-3 py-1.5 rounded-md bg-fg text-bg hover:opacity-90 inline-flex items-center gap-1.5">
          <FileSpreadsheet className="w-3.5 h-3.5" />
          Загрузить
        </Link>
      </Card>
    )
  }

  return (
    <Card className="p-3 bg-blue-50/30 border-blue-200/60 text-sm">
      <div className="flex items-start gap-3 mb-2">
        <FileSpreadsheet className="w-5 h-5 text-blue-700 mt-0.5 shrink-0" />
        <div className="flex-1">
          <strong className="text-blue-900">Покрытие XLSX «Экономика магазина»:</strong>
          <span className="text-xs text-fg-muted ml-2">наведи на ячейку для деталей</span>
        </div>
        <Link to="/finance/unit-economy/import"
              className="text-xs font-medium px-3 py-1.5 rounded-md border border-border-subtle hover:bg-bg-subtle inline-flex items-center gap-1.5 shrink-0">
          <FileSpreadsheet className="w-3.5 h-3.5" />
          Загрузить
        </Link>
      </div>
      <XlsxCoverageMatrix monthsBack={12} compact />
    </Card>
  )
}
