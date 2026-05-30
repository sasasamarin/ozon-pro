import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, ArrowUpRight, ArrowDownRight, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'

interface CashflowPoint {
  period_start: string
  inflow: number
  outflow: number
  net: number
  cumulative: number
}

interface CashflowKPI {
  total_inflow: number
  total_outflow: number
  net: number
  end_balance: number
}

interface CashflowResp {
  period_from: string
  period_to: string
  granularity: string
  kpi: CashflowKPI
  series: CashflowPoint[]
}

export function Cashflow() {
  const { selectedCabinetIds } = useCabinetStore()
  const [days, setDays] = useState(90)
  const [granularity, setGranularity] = useState<'day' | 'week' | 'month'>('week')

  const { data, isLoading } = useQuery<CashflowResp>({
    queryKey: ['cashflow', selectedCabinetIds, days, granularity],
    queryFn: async () => {
      const params = new URLSearchParams({
        days: String(days), granularity,
      })
      selectedCabinetIds.forEach((id) => params.append('cabinet_ids', id))
      const res = await api.get(`/finance/cashflow/?${params.toString()}`)
      return res.data
    },
  })

  const maxAbs = useMemo(() => {
    if (!data?.series?.length) return 1
    return Math.max(
      1,
      ...data.series.map((p) => Math.max(p.inflow, p.outflow))
    )
  }, [data])

  const formatDate = (s: string) => {
    const d = new Date(s)
    if (granularity === 'month') return d.toLocaleDateString('ru-RU', { month: 'short', year: '2-digit' })
    if (granularity === 'week') return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Cashflow</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Денежный поток по периодам · {data?.period_from} … {data?.period_to}
          </p>
        </div>
        <div className="flex gap-2">
          {[7, 28, 90, 180, 365].map((d) => (
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
              {d === 30 && '30 дней'}
              {d === 90 && '90 дней'}
              {d === 180 && '180 дней'}
              {d === 365 && 'Год'}
            </button>
          ))}
        </div>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiTile label="Приход" value={data?.kpi.total_inflow ?? 0} color="emerald" />
        <KpiTile label="Расход" value={data?.kpi.total_outflow ?? 0} color="rose" negative />
        <KpiTile label="Чистый поток" value={data?.kpi.net ?? 0} color="indigo" accent />
        <KpiTile label="Конечный баланс" value={data?.kpi.end_balance ?? 0} color="violet" />
      </div>

      <Card className="overflow-hidden">
        <div className="px-6 py-4 border-b border-border-subtle flex items-center justify-between flex-wrap gap-3">
          <div>
            <h2 className="text-base font-semibold text-fg flex items-center gap-2">
              <Activity className="w-4 h-4 text-fg-muted" />
              Поток по периодам
            </h2>
            <p className="text-xs text-fg-muted mt-0.5">Зелёные бары — приход, красные — расход</p>
          </div>
          <div className="flex gap-2">
            {(['day', 'week', 'month'] as const).map((g) => (
              <button
                key={g}
                onClick={() => setGranularity(g)}
                className={cn(
                  'px-3 py-1.5 rounded-md text-xs border transition-colors',
                  granularity === g
                    ? 'border-fg bg-fg text-bg'
                    : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
                )}
              >
                {g === 'day' && 'День'}
                {g === 'week' && 'Неделя'}
                {g === 'month' && 'Месяц'}
              </button>
            ))}
          </div>
        </div>

        {isLoading ? (
          <div className="py-16 flex justify-center items-center text-fg-muted">
            <Loader2 className="w-5 h-5 animate-spin mr-2" /> Загрузка…
          </div>
        ) : (data?.series.length ?? 0) === 0 ? (
          <div className="py-12 flex flex-col items-center text-fg-muted text-sm">
            <Activity className="w-8 h-8 mb-2 text-fg-subtle" />
            <p>Нет транзакций за период</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                  <th className="py-2.5 px-4 font-medium">период</th>
                  <th className="py-2.5 px-4 font-medium" style={{ width: '40%' }}>поток</th>
                  <th className="py-2.5 px-4 font-medium text-right">приход</th>
                  <th className="py-2.5 px-4 font-medium text-right">расход</th>
                  <th className="py-2.5 px-4 font-medium text-right">чистый</th>
                  <th className="py-2.5 px-4 font-medium text-right">накопит.</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {data!.series.map((p) => {
                  const inWidth = (p.inflow / maxAbs) * 100
                  const outWidth = (p.outflow / maxAbs) * 100
                  return (
                    <tr key={p.period_start} className="hover:bg-bg-subtle/40">
                      <td className="py-2.5 px-4 text-fg tabular-nums whitespace-nowrap">
                        {formatDate(p.period_start)}
                      </td>
                      <td className="py-2.5 px-4">
                        <div className="flex flex-col gap-0.5">
                          <div className="relative h-2.5 rounded bg-bg-subtle overflow-hidden">
                            <div className="absolute inset-y-0 left-1/2 bg-emerald-400" style={{ width: `${inWidth / 2}%` }} />
                          </div>
                          <div className="relative h-2.5 rounded bg-bg-subtle overflow-hidden">
                            <div className="absolute inset-y-0 right-1/2 bg-rose-400" style={{ width: `${outWidth / 2}%` }} />
                          </div>
                        </div>
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums text-emerald-700">
                        {formatCurrency(p.inflow)}
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums text-rose-700">
                        −{formatCurrency(p.outflow)}
                      </td>
                      <td className={cn(
                        'py-2.5 px-4 text-right tabular-nums font-semibold',
                        p.net >= 0 ? 'text-emerald-700' : 'text-rose-700',
                      )}>
                        {formatCurrency(p.net)}
                      </td>
                      <td className={cn(
                        'py-2.5 px-4 text-right tabular-nums font-mono',
                        p.cumulative >= 0 ? 'text-fg' : 'text-rose-700',
                      )}>
                        {formatCurrency(p.cumulative)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}

function KpiTile({
  label, value, color, negative, accent,
}: {
  label: string
  value: number
  color: 'emerald' | 'rose' | 'indigo' | 'violet'
  negative?: boolean
  accent?: boolean
}) {
  const colorMap = {
    emerald: 'text-emerald-700',
    rose: 'text-rose-700',
    indigo: 'text-indigo-700',
    violet: 'text-violet-700',
  }
  const displayValue = negative ? -value : value
  return (
    <Card className={cn('p-4', accent && 'border-2 border-indigo-200 bg-indigo-50/40')}>
      <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">{label}</p>
      <p className={cn('text-[22px] leading-tight font-semibold mt-1 tabular-nums', colorMap[color])}>
        {formatCurrency(displayValue)}
      </p>
    </Card>
  )
}
