/**
 * Помесячная сводка транзакций с drill-down: месяц → день → переход к
 * подробным операциям. Юзер: «не вываливай 85k строк сразу, начни помесячно».
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, ChevronDown, Loader2, TrendingUp, TrendingDown } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'

interface MonthRow {
  period: string
  inflow: number
  outflow: number
  net: number
  tx_count: number
}
interface MonthlyResp {
  months: MonthRow[]
  total_inflow: number
  total_outflow: number
  total_net: number
}
interface DayRow {
  date: string
  inflow: number
  outflow: number
  net: number
  tx_count: number
}

const MONTH_RU = (yyyymm: string) => {
  const [y, m] = yyyymm.split('-').map(Number)
  return new Date(y, (m || 1) - 1, 1).toLocaleDateString('ru-RU', {
    month: 'long', year: 'numeric',
  })
}

export function TransactionsMonthly() {
  const navigate = useNavigate()
  const { selectedCabinetIds } = useCabinetStore()
  const [expandedMonth, setExpandedMonth] = useState<string | null>(null)
  const [monthsBack, setMonthsBack] = useState(12)

  const { data, isLoading } = useQuery<MonthlyResp>({
    queryKey: ['transactions-monthly', selectedCabinetIds, monthsBack],
    queryFn: async () => {
      const p = new URLSearchParams({ months_back: String(monthsBack) })
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      return (await api.get(`/finance/transactions/monthly?${p.toString()}`)).data
    },
  })

  return (
    <Card className="overflow-hidden">
      <div className="px-5 py-3 border-b border-border-subtle flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-base font-semibold text-fg">Помесячная сводка</h2>
          <p className="text-[11px] text-fg-muted mt-0.5">
            Клик на месяц → разбивка по дням → клик на день → конкретные операции
          </p>
        </div>
        <div className="flex gap-1 text-xs">
          {[6, 12, 24].map((m) => (
            <button key={m} onClick={() => setMonthsBack(m)} className={cn(
              'px-2.5 py-1 rounded border',
              monthsBack === m ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle',
            )}>{m} мес</button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="py-16 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-fg-muted" /></div>
      ) : (data?.months.length ?? 0) === 0 ? (
        <div className="py-12 text-center text-sm text-fg-muted">Нет транзакций за период</div>
      ) : (
        <>
          {/* TOTAL header */}
          <div className="grid grid-cols-3 gap-3 px-5 py-3 bg-bg-subtle/30 border-b border-border-subtle">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-fg-muted">Всего входящие</div>
              <div className="text-lg font-semibold text-emerald-700 tabular-nums">
                {formatCurrency(data!.total_inflow)}
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-fg-muted">Всего списания</div>
              <div className="text-lg font-semibold text-rose-700 tabular-nums">
                −{formatCurrency(data!.total_outflow)}
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-fg-muted">Итого</div>
              <div className={cn('text-lg font-semibold tabular-nums',
                data!.total_net >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
                {data!.total_net >= 0 ? '+' : '−'}{formatCurrency(Math.abs(data!.total_net))}
              </div>
            </div>
          </div>

          <table className="w-full text-sm">
            <thead className="bg-bg-subtle/40 border-b border-border-subtle">
              <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                <th className="py-2.5 px-5 font-medium">Месяц</th>
                <th className="py-2.5 px-4 font-medium text-right">Поступления</th>
                <th className="py-2.5 px-4 font-medium text-right">Списания</th>
                <th className="py-2.5 px-4 font-medium text-right">Итого</th>
                <th className="py-2.5 px-4 font-medium text-right">Операций</th>
                <th className="py-2.5 px-2 w-8"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {data!.months.map((m) => {
                const expanded = expandedMonth === m.period
                return (
                  <>
                    <tr key={m.period}
                        onClick={() => setExpandedMonth(expanded ? null : m.period)}
                        className="hover:bg-bg-subtle/40 cursor-pointer">
                      <td className="py-2.5 px-5 font-medium text-fg capitalize">{MONTH_RU(m.period)}</td>
                      <td className="py-2.5 px-4 text-right tabular-nums text-emerald-700">
                        {formatCurrency(m.inflow)}
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums text-rose-700">
                        −{formatCurrency(m.outflow)}
                      </td>
                      <td className={cn('py-2.5 px-4 text-right tabular-nums font-semibold',
                        m.net >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
                        {m.net >= 0 ? '+' : '−'}{formatCurrency(Math.abs(m.net))}
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums text-fg-muted">
                        {formatNumber(m.tx_count)}
                      </td>
                      <td className="py-2.5 px-2 text-fg-subtle">
                        {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                      </td>
                    </tr>
                    {expanded && (
                      <tr key={`${m.period}-d`}>
                        <td colSpan={6} className="bg-bg-subtle/20 p-0">
                          <MonthDays period={m.period} cabinetIds={selectedCabinetIds}
                                     onDayClick={(d) => navigate(`/finance/transactions?date_from=${d}&date_to=${d}&view=all`)} />
                        </td>
                      </tr>
                    )}
                  </>
                )
              })}
            </tbody>
          </table>
        </>
      )}
    </Card>
  )
}

function MonthDays({
  period, cabinetIds, onDayClick,
}: {
  period: string
  cabinetIds: string[]
  onDayClick: (date: string) => void
}) {
  const { data, isLoading } = useQuery<DayRow[]>({
    queryKey: ['transactions-daily', period, cabinetIds],
    queryFn: async () => {
      const p = new URLSearchParams({ period })
      cabinetIds.forEach((id) => p.append('cabinet_ids', id))
      return (await api.get(`/finance/transactions/daily?${p.toString()}`)).data
    },
  })

  if (isLoading) {
    return <div className="py-6 text-center text-fg-muted text-xs">
      <Loader2 className="w-3.5 h-3.5 animate-spin inline" /> Загрузка дней…
    </div>
  }
  if ((data?.length ?? 0) === 0) {
    return <div className="py-6 text-center text-fg-muted text-xs">Нет операций в этом месяце</div>
  }

  return (
    <table className="w-full text-xs">
      <thead className="text-[10px] uppercase tracking-wider text-fg-subtle">
        <tr>
          <th className="py-1.5 px-5 text-left font-medium">День</th>
          <th className="py-1.5 px-4 text-right font-medium">Поступления</th>
          <th className="py-1.5 px-4 text-right font-medium">Списания</th>
          <th className="py-1.5 px-4 text-right font-medium">Итого</th>
          <th className="py-1.5 px-4 text-right font-medium">Опер.</th>
          <th className="py-1.5 px-2 w-8"></th>
        </tr>
      </thead>
      <tbody className="divide-y divide-border-subtle">
        {data!.map((d) => (
          <tr key={d.date}
              onClick={() => onDayClick(d.date)}
              className="hover:bg-bg-subtle/50 cursor-pointer"
              title="Клик → перейти к операциям этого дня">
            <td className="py-1.5 px-5 text-fg font-mono">{new Date(d.date).toLocaleDateString('ru-RU')}</td>
            <td className="py-1.5 px-4 text-right tabular-nums text-emerald-700">
              <span className="inline-flex items-center gap-1">
                {d.inflow > 0 && <TrendingUp className="w-3 h-3" />}
                {formatCurrency(d.inflow)}
              </span>
            </td>
            <td className="py-1.5 px-4 text-right tabular-nums text-rose-700">
              {d.outflow > 0 && (
                <span className="inline-flex items-center gap-1">
                  <TrendingDown className="w-3 h-3" />−{formatCurrency(d.outflow)}
                </span>
              )}
            </td>
            <td className={cn('py-1.5 px-4 text-right tabular-nums font-semibold',
              d.net >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
              {d.net >= 0 ? '+' : '−'}{formatCurrency(Math.abs(d.net))}
            </td>
            <td className="py-1.5 px-4 text-right tabular-nums text-fg-muted">{d.tx_count}</td>
            <td className="py-1.5 px-2 text-fg-subtle"><ChevronRight className="w-3 h-3" /></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
