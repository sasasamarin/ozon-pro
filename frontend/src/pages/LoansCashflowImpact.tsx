/**
 * /credits/cashflow-impact — влияние кредитов на cashflow.
 *
 * DSCR = чистый cashflow / платежи по кредитам.
 * Прогноз — proxy: тот же месяц годом ранее.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ComposedChart, Bar, Line, XAxis, YAxis, Tooltip, Legend,
  CartesianGrid, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { TrendingDown, AlertTriangle, CheckCircle2, Info } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { AskAIButton } from '@/components/AskAIButton'
import { api } from '@/lib/api'
import { formatCurrency, cn } from '@/lib/utils'

interface Item {
  month: string
  loan_payment_rub: number
  historical_net_cashflow_rub: number
  dscr: number | null
  risk: 'safe' | 'tight' | 'overload'
}
interface Resp {
  horizon_months: number
  items: Item[]
  summary: {
    total_loan_payments_rub: number
    total_hist_net_rub: number
    avg_dscr: number | null
    months_at_risk: number
    months_overload: number
    months_safe: number
    note: string
  }
}

const RISK_LABEL: Record<string, string> = {
  safe: 'безопасно', tight: 'напряжённо', overload: 'перегрузка',
}
const RISK_TONE: Record<string, string> = {
  safe: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  tight: 'bg-amber-50 text-amber-700 border-amber-200',
  overload: 'bg-rose-50 text-rose-700 border-rose-200',
}

export function LoansCashflowImpact() {
  const [horizon, setHorizon] = useState(12)
  const { data } = useQuery<Resp>({
    queryKey: ['loans-cashflow-impact', horizon],
    queryFn: async () =>
      (await api.get(`/loans/cashflow-impact?horizon_months=${horizon}`)).data,
  })

  const s = data?.summary
  const items = data?.items || []

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
            <TrendingDown className="w-6 h-6 text-amber-500" />
            Влияние кредитов на cashflow
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            DSCR = чистый поток / платёж по кредиту. Прогноз — тот же месяц годом ранее.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={horizon} onChange={(e) => setHorizon(+e.target.value)}
                  className="px-2 py-1 border border-border-subtle rounded text-sm bg-bg">
            <option value={6}>6 мес</option>
            <option value={12}>12 мес</option>
            <option value={24}>24 мес</option>
          </select>
          <AskAIButton
            context={{
              type: 'screen', source_page: 'loans-cashflow-impact',
              source_label: 'Влияние кредитов на cashflow',
              metrics: ['dscr', 'total_loan_payments', 'months_at_risk'],
            }}
            question="Какие месяцы рискованные? Хватит ли cashflow на платежи?"
            variant="solid"
          />
        </div>
      </div>

      {s && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Card className="p-3">
            <div className="text-xs text-fg-muted">Платежи (всего)</div>
            <div className="text-xl font-semibold tabular-nums">{formatCurrency(s.total_loan_payments_rub)}</div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-fg-muted">Прогноз cashflow</div>
            <div className={cn('text-xl font-semibold tabular-nums',
              s.total_hist_net_rub > 0 ? 'text-emerald-700' : 'text-rose-700')}>
              {formatCurrency(s.total_hist_net_rub)}
            </div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-fg-muted">Средний DSCR</div>
            <div className={cn('text-xl font-semibold tabular-nums',
              s.avg_dscr === null ? 'text-fg-muted' :
              s.avg_dscr >= 1.5 ? 'text-emerald-700' :
              s.avg_dscr >= 1 ? 'text-amber-700' : 'text-rose-700')}>
              {s.avg_dscr === null ? '—' : s.avg_dscr.toFixed(2)}
            </div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-fg-muted">Месяцев с риском</div>
            <div className={cn('text-xl font-semibold tabular-nums',
              s.months_at_risk > 0 ? 'text-rose-700' : 'text-emerald-700')}>
              {s.months_at_risk}
              {s.months_overload > 0 && (
                <span className="text-xs font-normal text-rose-700 ml-2">
                  (перегрузка: {s.months_overload})
                </span>
              )}
            </div>
          </Card>
        </div>
      )}

      <Card className="p-3 text-xs text-fg-muted flex items-start gap-2">
        <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
        {s?.note}
      </Card>

      <Card className="p-5">
        <h3 className="text-sm font-semibold text-fg mb-3">Платежи vs прогноз cashflow</h3>
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={items}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="month" tick={{ fontSize: 11 }} />
            <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} domain={[0, 'auto']} />
            <Tooltip formatter={(v: number, n: string) => {
              if (n === 'DSCR') return v?.toFixed?.(2) ?? '—'
              return formatCurrency(v as number)
            }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <ReferenceLine yAxisId="right" y={1} stroke="#ef4444" strokeDasharray="3 3" label={{ value: 'DSCR=1', fontSize: 10 }} />
            <ReferenceLine yAxisId="right" y={1.5} stroke="#10b981" strokeDasharray="3 3" label={{ value: 'DSCR=1.5', fontSize: 10 }} />
            <Bar yAxisId="left" dataKey="loan_payment_rub" fill="#f59e0b" name="Платёж" />
            <Bar yAxisId="left" dataKey="historical_net_cashflow_rub" fill="#6366f1" name="Cashflow (prognoz)" />
            <Line yAxisId="right" type="monotone" dataKey="dscr" stroke="#10b981" strokeWidth={2} name="DSCR" />
          </ComposedChart>
        </ResponsiveContainer>
      </Card>

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-fg-muted bg-bg-subtle/30">
            <tr>
              <th className="py-2 px-3 text-left">Месяц</th>
              <th className="py-2 px-3 text-right">Платёж</th>
              <th className="py-2 px-3 text-right">Cashflow (прогноз)</th>
              <th className="py-2 px-3 text-right">DSCR</th>
              <th className="py-2 px-3 text-center">Риск</th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.month} className={cn(
                'border-t border-border-subtle/40',
                i.risk === 'overload' && 'bg-rose-50/30',
              )}>
                <td className="py-2 px-3 font-mono text-xs">{i.month}</td>
                <td className="py-2 px-3 text-right tabular-nums">{formatCurrency(i.loan_payment_rub)}</td>
                <td className="py-2 px-3 text-right tabular-nums">{formatCurrency(i.historical_net_cashflow_rub)}</td>
                <td className="py-2 px-3 text-right tabular-nums">
                  {i.dscr === null ? '—' : i.dscr.toFixed(2)}
                </td>
                <td className="py-2 px-3 text-center">
                  <span className={cn('text-xs px-2 py-0.5 rounded border inline-flex items-center gap-1',
                    RISK_TONE[i.risk])}>
                    {i.risk === 'overload' && <AlertTriangle className="w-3 h-3" />}
                    {i.risk === 'safe' && <CheckCircle2 className="w-3 h-3" />}
                    {RISK_LABEL[i.risk]}
                  </span>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={5} className="py-6 text-center text-fg-muted">Нет платежей по кредитам.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
