import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Store, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { DateRangeBar } from '@/components/DateRangeBar'

interface Row {
  cabinet_id: string
  cabinet_name: string
  premium_tier: string
  sku_count: number
  revenue: number
  orders: number
  aov: number
  cogs: number
  ozon_expenses: number
  marginal_profit: number
  margin_pct: number | null
}

interface Resp {
  period_from: string
  period_to: string
  rows: Row[]
}

export function Summary() {
  const [days, setDays] = useState(30)
  const { data, isLoading } = useQuery<Resp>({
    queryKey: ['summary', days],
    queryFn: async () => (await api.get(`/analytics/summary/?days=${days}`)).data,
  })

  const totalRevenue = (data?.rows || []).reduce((s, r) => s + r.revenue, 0)
  const totalProfit = (data?.rows || []).reduce((s, r) => s + r.marginal_profit, 0)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Сводка по магазинам</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            {data?.rows.length ?? 0} кабинетов · {data?.period_from} … {data?.period_to}
          </p>
        </div>
        <div className="flex gap-2">
          <DateRangeBar days={days} onChange={setDays} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Card className="p-4">
          <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">Суммарная выручка</p>
          <p className="text-[22px] font-semibold text-emerald-700 mt-1 tabular-nums">{formatCurrency(totalRevenue)}</p>
        </Card>
        <Card className="p-4">
          <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">Маржинальная прибыль</p>
          <p className="text-[22px] font-semibold text-indigo-700 mt-1 tabular-nums">{formatCurrency(totalProfit)}</p>
        </Card>
      </div>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 flex justify-center text-fg-muted"><Loader2 className="w-5 h-5 animate-spin" /></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                  <th className="py-2.5 px-4 font-medium">кабинет</th>
                  <th className="py-2.5 px-4 font-medium text-right">SKU</th>
                  <th className="py-2.5 px-4 font-medium text-right">выручка</th>
                  <th className="py-2.5 px-4 font-medium text-right">заказы</th>
                  <th className="py-2.5 px-4 font-medium text-right">AOV</th>
                  <th className="py-2.5 px-4 font-medium text-right">COGS</th>
                  <th className="py-2.5 px-4 font-medium text-right">расходы Ozon</th>
                  <th className="py-2.5 px-4 font-medium text-right">маржинальная</th>
                  <th className="py-2.5 px-4 font-medium text-right">маржа %</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {(data?.rows || []).map((r) => (
                  <tr key={r.cabinet_id} className="hover:bg-bg-subtle/40">
                    <td className="py-2.5 px-4">
                      <div className="flex items-center gap-2">
                        <Store className="w-4 h-4 text-fg-subtle" />
                        <div>
                          <div className="font-medium text-fg">{r.cabinet_name}</div>
                          <div className="text-[10px] text-fg-subtle uppercase">{r.premium_tier.replace('_', ' ')}</div>
                        </div>
                      </div>
                    </td>
                    <td className="py-2.5 px-4 text-right tabular-nums">{r.sku_count}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums text-emerald-700">{formatCurrency(r.revenue)}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums">{formatNumber(r.orders)}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums text-fg-muted">{formatCurrency(r.aov)}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums text-rose-700">−{formatCurrency(r.cogs)}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums text-rose-700">−{formatCurrency(r.ozon_expenses)}</td>
                    <td className={cn('py-2.5 px-4 text-right tabular-nums font-semibold',
                      r.marginal_profit >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
                      {formatCurrency(r.marginal_profit)}
                    </td>
                    <td className={cn('py-2.5 px-4 text-right tabular-nums font-mono',
                      (r.margin_pct ?? 0) >= 0 ? 'text-fg' : 'text-rose-700')}>
                      {r.margin_pct != null ? `${r.margin_pct}%` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
