import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Landmark, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'

interface BalancePoint {
  date: string
  inflow: number
  outflow: number
  net: number
  cumulative: number
}

interface BalanceResp {
  period_from: string
  period_to: string
  starting_balance: number
  current_balance: number
  total_inflow: number
  total_outflow: number
  series: BalancePoint[]
}

export function AccountBalance() {
  const { selectedCabinetIds } = useCabinetStore()
  const [days, setDays] = useState(180)

  const { data, isLoading } = useQuery<BalanceResp>({
    queryKey: ['account-balance', selectedCabinetIds, days],
    queryFn: async () => {
      const p = new URLSearchParams({ days: String(days) })
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      return (await api.get(`/finance/account-balance/?${p.toString()}`)).data
    },
  })

  const minCum = Math.min(0, ...(data?.series || []).map((s) => s.cumulative))
  const maxCum = Math.max(0, ...(data?.series || []).map((s) => s.cumulative))
  const range = Math.max(1, maxCum - minCum)

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Баланс Ozon</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Накопительный баланс счёта из transactions
          </p>
        </div>
        <div className="flex gap-2">
          {[30, 90, 180, 365].map((d) => (
            <button key={d} onClick={() => setDays(d)} className={cn(
              'px-3 py-1.5 rounded-md text-sm border transition-colors',
              days === d ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
            )}>
              {d}д
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Card className="p-4">
          <p className="text-[11px] uppercase text-fg-muted">Начальный баланс</p>
          <p className="text-xl font-semibold mt-1 tabular-nums">{formatCurrency(data?.starting_balance ?? 0)}</p>
        </Card>
        <Card className="p-4">
          <p className="text-[11px] uppercase text-fg-muted">Приход</p>
          <p className="text-xl font-semibold text-emerald-700 mt-1 tabular-nums">{formatCurrency(data?.total_inflow ?? 0)}</p>
        </Card>
        <Card className="p-4">
          <p className="text-[11px] uppercase text-fg-muted">Расход</p>
          <p className="text-xl font-semibold text-rose-700 mt-1 tabular-nums">−{formatCurrency(data?.total_outflow ?? 0)}</p>
        </Card>
        <Card className="p-4 border-2 border-indigo-200 bg-indigo-50/40">
          <p className="text-[11px] uppercase text-fg-muted">Текущий баланс</p>
          <p className={cn(
            'text-xl font-semibold mt-1 tabular-nums',
            (data?.current_balance ?? 0) >= 0 ? 'text-emerald-700' : 'text-rose-700',
          )}>{formatCurrency(data?.current_balance ?? 0)}</p>
        </Card>
      </div>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 flex justify-center"><Loader2 className="w-5 h-5 animate-spin" /></div>
        ) : (data?.series.length ?? 0) === 0 ? (
          <div className="py-12 flex flex-col items-center text-fg-muted text-sm">
            <Landmark className="w-8 h-8 mb-2 text-fg-subtle" />
            <p>Нет транзакций</p>
          </div>
        ) : (
          <div className="p-5">
            <h2 className="text-base font-semibold text-fg mb-4">Динамика баланса</h2>
            <div className="overflow-x-auto pb-2">
              <div className="flex items-end gap-0.5 min-w-[600px] h-[180px]" style={{
                position: 'relative',
              }}>
                {data!.series.map((s) => {
                  const heightPct = ((s.cumulative - minCum) / range) * 100
                  const isNeg = s.cumulative < 0
                  return (
                    <div key={s.date} className="flex-1 min-w-[2px] flex flex-col items-center"
                         title={`${s.date}: ${formatCurrency(s.cumulative)} (net ${formatCurrency(s.net)})`}>
                      <div className="w-full relative" style={{ height: '180px' }}>
                        <div className={cn(
                          'absolute w-full bottom-0 rounded-t-sm',
                          isNeg ? 'bg-rose-300' : 'bg-emerald-300',
                        )} style={{ height: `${heightPct}%` }} />
                      </div>
                    </div>
                  )
                })}
              </div>
              <div className="flex justify-between text-[10px] text-fg-subtle mt-2 font-mono">
                <span>{data!.series[0]?.date}</span>
                <span>{data!.series[data!.series.length - 1]?.date}</span>
              </div>
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-bg-subtle/50">
                  <tr className="text-left text-fg-muted uppercase tracking-wider">
                    <th className="py-2 px-3">дата</th>
                    <th className="py-2 px-3 text-right">приход</th>
                    <th className="py-2 px-3 text-right">расход</th>
                    <th className="py-2 px-3 text-right">net</th>
                    <th className="py-2 px-3 text-right">накопит.</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {data!.series.slice().reverse().slice(0, 30).map((s) => (
                    <tr key={s.date} className="hover:bg-bg-subtle/40">
                      <td className="py-2 px-3 font-mono">{s.date}</td>
                      <td className="py-2 px-3 text-right tabular-nums text-emerald-700">{formatCurrency(s.inflow)}</td>
                      <td className="py-2 px-3 text-right tabular-nums text-rose-700">−{formatCurrency(s.outflow)}</td>
                      <td className={cn('py-2 px-3 text-right tabular-nums font-semibold',
                        s.net >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
                        {formatCurrency(s.net)}
                      </td>
                      <td className={cn('py-2 px-3 text-right tabular-nums font-mono',
                        s.cumulative >= 0 ? 'text-fg' : 'text-rose-700')}>
                        {formatCurrency(s.cumulative)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
