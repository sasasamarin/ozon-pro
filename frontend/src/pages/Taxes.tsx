/**
 * /finance/taxes — расчёт налога за период по настройкам компании.
 * Использует services/tax.py:calc_tax (тот же что в P&L).
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Receipt, AlertCircle } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { AskAIButton } from '@/components/AskAIButton'
import { api } from '@/lib/api'
import { useCabinetStore } from '@/stores/cabinet'
import { formatCurrency, cn } from '@/lib/utils'

interface Resp {
  period_from: string; period_to: string
  regime: string; regime_label: string
  rate_pct: number; vat_rate_pct: number | null
  revenue: number; expenses: number; gross_profit: number
  tax_amount: number; vat_amount: number; net_profit_after_tax: number
  monthly_breakdown: { month: string; revenue: number; tax_estimate: number }[]
  note: string
}

export function Taxes() {
  const { selectedCabinetIds } = useCabinetStore()
  const [days, setDays] = useState(30)
  const { data } = useQuery<Resp>({
    queryKey: ['taxes', days],
    queryFn: async () => (await api.get(`/taxes/?days=${days}`)).data,
  })

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
            <Receipt className="w-6 h-6 text-blue-500" />
            Налоги
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            Расчёт по настройкам компании. Точная цифра — после закрытия отчётного периода Ozon.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={days} onChange={(e) => setDays(+e.target.value)}
                  className="px-2 py-1 border border-border-subtle rounded text-sm bg-bg">
            <option value={30}>30 дней</option>
            <option value={90}>квартал</option>
            <option value={365}>год</option>
          </select>
          <AskAIButton
            context={{
              type: 'screen', source_page: 'taxes', source_label: 'Налоги',
              metrics: ['revenue', 'gross_profit', 'tax_amount', 'net_profit_after_tax'],
              period: data ? { from: data.period_from, to: data.period_to } : undefined,
              cabinet_ids: selectedCabinetIds,
            }}
            question="Сколько уйдёт на налоги? Можно оптимизировать?"
            variant="solid"
          />
        </div>
      </div>

      {data && (
        <>
          <Card className="p-4 bg-blue-50/30 border-blue-200 text-sm flex items-start gap-3">
            <AlertCircle className="w-4 h-4 mt-0.5 text-blue-600 shrink-0" />
            <div>
              <b>{data.regime_label}</b> · ставка {data.rate_pct}%
              {data.vat_rate_pct ? ` · НДС ${data.vat_rate_pct}%` : ''}
              <div className="text-xs text-fg-muted mt-1">{data.note}</div>
            </div>
          </Card>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="Выручка" value={data.revenue} tone="fg" />
            <Stat label="Прибыль до налога" value={data.gross_profit} tone={data.gross_profit > 0 ? 'emerald' : 'rose'} />
            <Stat label="Налог" value={data.tax_amount} tone="amber" />
            <Stat label="Чистая после налога" value={data.net_profit_after_tax} tone={data.net_profit_after_tax > 0 ? 'emerald' : 'rose'} />
          </div>

          {/* Помесячно */}
          {data.monthly_breakdown.length > 0 && (
            <Card className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-fg-muted bg-bg-subtle/30">
                  <tr>
                    <th className="py-2 px-3 text-left">Месяц</th>
                    <th className="py-2 px-3 text-right">Выручка</th>
                    <th className="py-2 px-3 text-right">Налог (оценка)</th>
                  </tr>
                </thead>
                <tbody>
                  {data.monthly_breakdown.map((m) => (
                    <tr key={m.month} className="border-t border-border-subtle/40">
                      <td className="py-2 px-3">{m.month}</td>
                      <td className="py-2 px-3 text-right tabular-nums">{formatCurrency(m.revenue)}</td>
                      <td className="py-2 px-3 text-right tabular-nums text-amber-700">{formatCurrency(m.tax_estimate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </>
      )}
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: number; tone: 'fg' | 'emerald' | 'rose' | 'amber' }) {
  return (
    <Card className="p-3">
      <div className="text-xs text-fg-muted">{label}</div>
      <div className={cn('text-xl font-semibold mt-0.5 tabular-nums',
        tone === 'emerald' && 'text-emerald-700',
        tone === 'rose' && 'text-rose-700',
        tone === 'amber' && 'text-amber-700',
      )}>{formatCurrency(value)}</div>
    </Card>
  )
}
