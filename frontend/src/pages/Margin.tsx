/**
 * /finance/margin — маржа per-SKU.
 *
 * Источник: products.cost_price + marketing_seller_price + actual order_items
 * (delivered) + средние коэффициенты МП-расходов из services/finance_consts.py.
 *
 * Для точной маржи нужна себестоимость — без неё в строке cost_known=false.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Percent, AlertCircle, TrendingDown, TrendingUp } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { AskAIButton } from '@/components/AskAIButton'
import { api } from '@/lib/api'
import { useCabinetStore } from '@/stores/cabinet'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { MetricLabel } from '@/components/MetricLabel'

interface MarginRow {
  product_id: string
  name: string | null
  offer_id: string | null
  ozon_sku: number | null
  cabinet_name: string
  seller_price_rub: number | null
  cost_price_rub: number | null
  cost_known: boolean
  delivered_units: number
  revenue_rub: number
  avg_mp_costs_per_unit_rub: number | null
  gross_margin_per_unit_rub: number | null
  gross_margin_pct: number | null
  note: string
}

interface Resp {
  period_days: number
  items: MarginRow[]
  summary: {
    total_revenue_rub: number
    total_gross_margin_rub: number
    gross_margin_pct: number | null
    skus_total: number
    skus_with_cost: number
    skus_without_cost: number
    note: string
  }
}

export function Margin() {
  const { selectedCabinetIds } = useCabinetStore()
  const cabinetId = selectedCabinetIds[0] || null
  const [days, setDays] = useState(30)

  const { data } = useQuery<Resp>({
    queryKey: ['margin', cabinetId, days],
    queryFn: async () => {
      const p = new URLSearchParams({ days: String(days) })
      if (cabinetId) p.append('cabinet_id', cabinetId)
      return (await api.get(`/margin/?${p.toString()}`)).data
    },
  })

  const items = data?.items || []
  const s = data?.summary

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
            <Percent className="w-6 h-6 text-emerald-500" />
            Маржинальность
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            Маржа per-SKU = seller_price − cost_price − средние МП-расходы.
            Точная цифра доступна только для SKU с заведённой себестоимостью.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={days} onChange={(e) => setDays(+e.target.value)}
                  className="px-2 py-1 border border-border-subtle rounded text-sm bg-bg">
            <option value={7}>7 дней</option>
            <option value={30}>30 дней</option>
            <option value={90}>90 дней</option>
          </select>
          <AskAIButton
            context={{
              type: 'table',
              source_page: 'margin',
              source_label: 'Маржа per-SKU',
              metrics: ['gross_margin_pct', 'gross_margin_per_unit_rub', 'cost_price_rub', 'seller_price_rub'],
              cabinet_ids: selectedCabinetIds,
            }}
            question="Какие SKU убыточны? Где маржа критическая?"
            variant="solid"
          />
        </div>
      </div>

      {/* Summary */}
      {s && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Card className="p-3">
            <div className="text-xs text-fg-muted">
              <MetricLabel metricKey="revenue" override={`Выручка (${days}д)`} />
            </div>
            <div className="text-lg font-semibold tabular-nums">{formatCurrency(s.total_revenue_rub)}</div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-fg-muted">
              <MetricLabel metricKey="gross_profit" override="Валовая маржа" />
            </div>
            <div className="text-lg font-semibold tabular-nums">{formatCurrency(s.total_gross_margin_rub)}</div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-fg-muted">
              <MetricLabel metricKey="gross_margin_pct" override="Маржа %" />
            </div>
            <div className="text-lg font-semibold tabular-nums">
              {s.gross_margin_pct !== null ? `${s.gross_margin_pct.toFixed(1)}%` : '—'}
            </div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-fg-muted">SKU с себестоимостью</div>
            <div className="text-lg font-semibold tabular-nums">
              <span className="text-emerald-700">{s.skus_with_cost}</span>
              <span className="text-fg-muted"> / {s.skus_total}</span>
            </div>
            {s.skus_without_cost > 0 && (
              <div className="text-[11px] text-amber-700">{s.skus_without_cost} без cost — заведи в /products</div>
            )}
          </Card>
        </div>
      )}

      {s?.note && (
        <Card className="p-3 text-xs text-fg-muted flex items-start gap-2">
          <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          {s.note}
        </Card>
      )}

      {/* Table */}
      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-fg-muted bg-bg-subtle/30">
            <tr>
              <th className="py-2 px-3 text-left">SKU</th>
              <th className="py-2 px-3 text-right">Доставлено</th>
              <th className="py-2 px-3 text-right">Выручка</th>
              <th className="py-2 px-3 text-right">Цена продавца</th>
              <th className="py-2 px-3 text-right">Себестоимость</th>
              <th className="py-2 px-3 text-right">МП/шт</th>
              <th className="py-2 px-3 text-right">Маржа/шт</th>
              <th className="py-2 px-3 text-right">Маржа %</th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => {
              const negMargin = i.gross_margin_per_unit_rub !== null && i.gross_margin_per_unit_rub < 0
              const lowMargin = i.gross_margin_pct !== null && i.gross_margin_pct >= 0 && i.gross_margin_pct < 10
              return (
                <tr key={i.product_id} className={cn(
                  'border-t border-border-subtle/40 hover:bg-bg-subtle/20',
                  negMargin && 'bg-rose-50/30',
                )}>
                  <td className="py-2 px-3 max-w-[300px]">
                    <div className="text-fg truncate" title={i.name || ''}>{i.name?.slice(0, 50)}</div>
                    <div className="text-[10px] text-fg-muted">{i.offer_id} · {i.cabinet_name}</div>
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums">{formatNumber(i.delivered_units)}</td>
                  <td className="py-2 px-3 text-right tabular-nums">{formatCurrency(i.revenue_rub)}</td>
                  <td className="py-2 px-3 text-right tabular-nums">
                    {i.seller_price_rub ? formatCurrency(i.seller_price_rub) : '—'}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums">
                    {i.cost_known ? formatCurrency(i.cost_price_rub!) : <span className="text-fg-subtle">—</span>}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-fg-muted">
                    {i.avg_mp_costs_per_unit_rub ? formatCurrency(i.avg_mp_costs_per_unit_rub) : '—'}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums">
                    {i.gross_margin_per_unit_rub !== null ? (
                      <span className={cn(negMargin && 'text-rose-700 font-semibold')}>
                        {formatCurrency(i.gross_margin_per_unit_rub)}
                      </span>
                    ) : <span className="text-fg-subtle">нет cost</span>}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums">
                    {i.gross_margin_pct !== null ? (
                      <span className={cn(
                        'inline-flex items-center gap-0.5',
                        negMargin && 'text-rose-700 font-semibold',
                        lowMargin && 'text-amber-700',
                        !negMargin && !lowMargin && 'text-emerald-700',
                      )}>
                        {negMargin && <TrendingDown className="w-3 h-3" />}
                        {!negMargin && i.gross_margin_pct >= 30 && <TrendingUp className="w-3 h-3" />}
                        {i.gross_margin_pct.toFixed(1)}%
                      </span>
                    ) : '—'}
                  </td>
                </tr>
              )
            })}
            {items.length === 0 && (
              <tr><td colSpan={8} className="py-6 text-center text-fg-muted">Нет данных за период.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
