/**
 * /procurement/quality — качество поставок.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Shield, AlertTriangle, Info } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { AskAIButton } from '@/components/AskAIButton'
import { api } from '@/lib/api'
import { formatNumber, cn } from '@/lib/utils'

interface SupplierQ {
  supplier_id: string | null; supplier_name: string
  products_count: number; units_supplied: number; units_returned: number
  return_rate_pct: number; avg_lead_time_days: number | null
  overdue_orders: number; avg_overdue_days: number | null
}
interface ProblemProd {
  product_id: string; product_name: string; offer_id: string
  supplier_name: string | null
  units_supplied: number; units_returned: number
  return_rate_pct: number; top_reason: string | null
}
interface Resp {
  period_from: string; period_to: string
  suppliers: SupplierQ[]; problem_products: ProblemProd[]
  summary: {
    total_supplied: number; total_returned: number
    overall_return_rate_pct: number; suppliers_count: number
    note: string
  }
}

function rateTone(rate: number) {
  if (rate >= 10) return 'text-rose-700 bg-rose-50'
  if (rate >= 5) return 'text-amber-700 bg-amber-50'
  return 'text-emerald-700 bg-emerald-50'
}

export function ProcurementQuality() {
  const [days, setDays] = useState(180)
  const { data } = useQuery<Resp>({
    queryKey: ['procurement-quality', days],
    queryFn: async () =>
      (await api.get(`/procurement/quality/quality?days=${days}`)).data,
  })

  const s = data?.summary
  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
            <Shield className="w-6 h-6 text-blue-500" />
            Контроль качества поставок
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            % возвратов от покупателей по поставщикам и SKU.
            Не различает дефект и «не подошёл» — смотри top_reason.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={days} onChange={(e) => setDays(+e.target.value)}
                  className="px-2 py-1 border border-border-subtle rounded text-sm bg-bg">
            <option value={90}>90д</option>
            <option value={180}>180д</option>
            <option value={365}>год</option>
          </select>
          <AskAIButton
            context={{ type: 'screen', source_page: 'procurement-quality',
              source_label: 'Контроль качества',
              metrics: ['return_rate_pct', 'overdue_orders', 'avg_lead_time_days'] }}
            question="Какой поставщик хуже всех? Кого пора менять?"
          />
        </div>
      </div>

      {s && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Card className="p-3">
            <div className="text-xs text-fg-muted">Поставлено</div>
            <div className="text-xl font-semibold tabular-nums">{formatNumber(s.total_supplied)}</div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-fg-muted">Возвращено</div>
            <div className="text-xl font-semibold tabular-nums">{formatNumber(s.total_returned)}</div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-fg-muted">% возврата (общий)</div>
            <div className={cn('text-xl font-semibold tabular-nums',
              s.overall_return_rate_pct >= 10 ? 'text-rose-700' :
              s.overall_return_rate_pct >= 5 ? 'text-amber-700' : 'text-emerald-700')}>
              {s.overall_return_rate_pct.toFixed(2)}%
            </div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-fg-muted">Поставщиков</div>
            <div className="text-xl font-semibold tabular-nums">{s.suppliers_count}</div>
          </Card>
        </div>
      )}

      <Card className="p-3 text-xs text-fg-muted flex items-start gap-2">
        <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
        {s?.note}
      </Card>

      {/* Suppliers */}
      <Card>
        <div className="p-3 border-b border-border-subtle">
          <h3 className="text-sm font-semibold">Сводка по поставщикам</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-fg-muted bg-bg-subtle/30">
              <tr>
                <th className="py-2 px-3 text-left">Поставщик</th>
                <th className="py-2 px-3 text-right">SKU</th>
                <th className="py-2 px-3 text-right">Поставлено</th>
                <th className="py-2 px-3 text-right">Возвраты</th>
                <th className="py-2 px-3 text-right">% возврата</th>
                <th className="py-2 px-3 text-right">Lead-time</th>
                <th className="py-2 px-3 text-right">Просрочено</th>
              </tr>
            </thead>
            <tbody>
              {(data?.suppliers || []).map((sup) => (
                <tr key={sup.supplier_id || sup.supplier_name} className="border-t border-border-subtle/40">
                  <td className="py-2 px-3 font-medium">{sup.supplier_name}</td>
                  <td className="py-2 px-3 text-right tabular-nums">{sup.products_count}</td>
                  <td className="py-2 px-3 text-right tabular-nums">{formatNumber(sup.units_supplied)}</td>
                  <td className="py-2 px-3 text-right tabular-nums">{formatNumber(sup.units_returned)}</td>
                  <td className="py-2 px-3 text-right">
                    <span className={cn('px-2 py-0.5 rounded text-xs', rateTone(sup.return_rate_pct))}>
                      {sup.return_rate_pct.toFixed(2)}%
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-fg-muted">
                    {sup.avg_lead_time_days?.toFixed(1) || '—'}д
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums">
                    {sup.overdue_orders > 0 ? (
                      <span className="text-rose-700">
                        {sup.overdue_orders} · +{sup.avg_overdue_days?.toFixed(0)}д
                      </span>
                    ) : <span className="text-emerald-700">—</span>}
                  </td>
                </tr>
              ))}
              {(data?.suppliers || []).length === 0 && (
                <tr><td colSpan={7} className="py-6 text-center text-fg-muted">Нет данных за период.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Problem products */}
      {data && data.problem_products.length > 0 && (
        <Card>
          <div className="p-3 border-b border-border-subtle">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              Топ-20 проблемных SKU
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-fg-muted bg-bg-subtle/30">
                <tr>
                  <th className="py-2 px-3 text-left">Товар</th>
                  <th className="py-2 px-3 text-left">Поставщик</th>
                  <th className="py-2 px-3 text-right">Поставлено</th>
                  <th className="py-2 px-3 text-right">Возвраты</th>
                  <th className="py-2 px-3 text-right">% возврата</th>
                  <th className="py-2 px-3 text-left">Топ-причина</th>
                </tr>
              </thead>
              <tbody>
                {data.problem_products.map((p) => (
                  <tr key={p.product_id} className="border-t border-border-subtle/40">
                    <td className="py-2 px-3 max-w-[280px] truncate" title={p.product_name}>
                      <div>{p.product_name}</div>
                      <div className="text-[10px] text-fg-muted">{p.offer_id}</div>
                    </td>
                    <td className="py-2 px-3 text-xs text-fg-muted">{p.supplier_name || '—'}</td>
                    <td className="py-2 px-3 text-right tabular-nums">{formatNumber(p.units_supplied)}</td>
                    <td className="py-2 px-3 text-right tabular-nums">{formatNumber(p.units_returned)}</td>
                    <td className="py-2 px-3 text-right">
                      <span className={cn('px-2 py-0.5 rounded text-xs', rateTone(p.return_rate_pct))}>
                        {p.return_rate_pct.toFixed(2)}%
                      </span>
                    </td>
                    <td className="py-2 px-3 text-xs text-fg-muted max-w-[200px] truncate">
                      {p.top_reason || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
