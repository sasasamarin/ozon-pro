/**
 * /credits/schedule — график платежей по всем кредитам.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip,
  CartesianGrid, Legend,
} from 'recharts'
import { CalendarClock, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { AskAIButton } from '@/components/AskAIButton'
import { api } from '@/lib/api'
import { useCabinetStore } from '@/stores/cabinet'
import { formatCurrency, cn } from '@/lib/utils'

interface PaymentRow {
  payment_id: string
  loan_id: string
  lender: string | null
  seq: number
  pay_date: string
  principal_part: number
  interest_part: number
  fee_part: number
  total: number
  is_paid: boolean
  overdue_days: number
}
interface MonthAgg {
  month: string
  total_due: number
  principal: number
  interest: number
  fee: number
  payments_count: number
  paid_count: number
}
interface Resp {
  items: PaymentRow[]
  by_month: MonthAgg[]
  summary: {
    total_payments: number
    overdue_count: number
    total_due_rub: number
    total_paid_rub: number
    next_payment_date: string | null
    next_payment_amount_rub: number | null
    next_payment_lender: string | null
  }
}

export function LoansSchedule() {
  const { selectedCabinetIds } = useCabinetStore()
  const [onlyUnpaid, setOnlyUnpaid] = useState(true)
  const { data } = useQuery<Resp>({
    queryKey: ['loans-schedule', onlyUnpaid],
    queryFn: async () => (await api.get(`/loans/schedule?only_unpaid=${onlyUnpaid}`)).data,
  })

  const items = data?.items || []
  const s = data?.summary

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
            <CalendarClock className="w-6 h-6 text-blue-500" />
            График платежей
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            Все запланированные платежи по кредитам. Тело займа — в Cashflow, проценты — в P&L.
          </p>
        </div>
        <AskAIButton
          context={{
            type: 'screen', source_page: 'loans-schedule',
            source_label: 'График платежей',
            metrics: ['total_due', 'overdue', 'principal', 'interest'],
            cabinet_ids: selectedCabinetIds,
          }}
          question="Сможем ли вытянуть платежи по cashflow? Где риски?"
          variant="solid"
        />
      </div>

      {s && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Card className="p-3">
            <div className="text-xs text-fg-muted">К оплате (всего)</div>
            <div className="text-xl font-semibold tabular-nums text-fg">{formatCurrency(s.total_due_rub)}</div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-fg-muted">Оплачено</div>
            <div className="text-xl font-semibold tabular-nums text-emerald-700">{formatCurrency(s.total_paid_rub)}</div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-fg-muted">Просрочено</div>
            <div className={cn('text-xl font-semibold tabular-nums',
              s.overdue_count > 0 ? 'text-rose-700' : 'text-emerald-700')}>{s.overdue_count}</div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-fg-muted">Ближайший платёж</div>
            {s.next_payment_date ? (
              <>
                <div className="text-lg font-semibold tabular-nums">{formatCurrency(s.next_payment_amount_rub || 0)}</div>
                <div className="text-[11px] text-fg-muted">{s.next_payment_date} · {s.next_payment_lender}</div>
              </>
            ) : (
              <div className="text-sm text-fg-muted">—</div>
            )}
          </Card>
        </div>
      )}

      {/* Помесячный график */}
      {data && data.by_month.length > 0 && (
        <Card className="p-5">
          <h3 className="text-sm font-semibold text-fg mb-3">Платежи помесячно</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data.by_month}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="month" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v: number) => formatCurrency(v)} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="principal" stackId="a" fill="#6366f1" name="Тело" />
              <Bar dataKey="interest" stackId="a" fill="#f59e0b" name="Проценты" />
              <Bar dataKey="fee" stackId="a" fill="#ef4444" name="Комиссии" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      <Card className="p-3 flex items-center justify-between text-sm">
        <label className="inline-flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={onlyUnpaid}
            onChange={(e) => setOnlyUnpaid(e.target.checked)} className="rounded" />
          <span>Только неоплаченные</span>
        </label>
        <span className="text-xs text-fg-muted">{items.length} платежей</span>
      </Card>

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-fg-muted bg-bg-subtle/30">
            <tr>
              <th className="py-2 px-3 text-left">Дата</th>
              <th className="py-2 px-3 text-left">Кредитор</th>
              <th className="py-2 px-3 text-center">№</th>
              <th className="py-2 px-3 text-right">Тело</th>
              <th className="py-2 px-3 text-right">Проценты</th>
              <th className="py-2 px-3 text-right">Комиссия</th>
              <th className="py-2 px-3 text-right">Итого</th>
              <th className="py-2 px-3 text-center">Статус</th>
            </tr>
          </thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.payment_id} className={cn(
                'border-t border-border-subtle/40',
                p.overdue_days > 0 && 'bg-rose-50/30',
              )}>
                <td className="py-2 px-3 font-mono text-xs">{p.pay_date}</td>
                <td className="py-2 px-3 text-xs">{p.lender || '—'}</td>
                <td className="py-2 px-3 text-center text-fg-muted text-xs">{p.seq}</td>
                <td className="py-2 px-3 text-right tabular-nums">{formatCurrency(p.principal_part)}</td>
                <td className="py-2 px-3 text-right tabular-nums">{formatCurrency(p.interest_part)}</td>
                <td className="py-2 px-3 text-right tabular-nums">{formatCurrency(p.fee_part)}</td>
                <td className="py-2 px-3 text-right tabular-nums font-medium">{formatCurrency(p.total)}</td>
                <td className="py-2 px-3 text-center">
                  {p.is_paid ? (
                    <span className="inline-flex items-center gap-1 text-emerald-700 text-xs">
                      <CheckCircle2 className="w-3 h-3" /> оплачен
                    </span>
                  ) : p.overdue_days > 0 ? (
                    <span className="inline-flex items-center gap-1 text-rose-700 text-xs font-semibold">
                      <AlertTriangle className="w-3 h-3" /> просрочка {p.overdue_days}д
                    </span>
                  ) : (
                    <span className="text-xs text-fg-muted">в графике</span>
                  )}
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={8} className="py-6 text-center text-fg-muted">Кредитов нет.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
