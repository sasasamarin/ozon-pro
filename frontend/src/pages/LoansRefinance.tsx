/**
 * /credits/refinance — калькулятор рефинансирования.
 */
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Repeat, TrendingDown, TrendingUp, Calculator, Info } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { AskAIButton } from '@/components/AskAIButton'
import { api } from '@/lib/api'
import { formatCurrency, cn } from '@/lib/utils'

interface LoanCmp {
  loan_id: string; lender: string | null
  current_remaining_principal: number
  current_rate_pct: number
  current_payments_left: number
  current_remaining_payments_sum: number
  current_remaining_interest: number
}
interface RefiResp {
  current: LoanCmp[]
  current_total_remaining: number
  current_total_payments_left_sum: number
  current_total_interest_left: number
  new_principal: number
  new_monthly_payment: number
  new_total_payments_sum: number
  new_total_interest: number
  savings_rub: number
  savings_pct: number
  recommendation: string
  breakeven_months: number | null
  note: string
}

export function LoansRefinance() {
  const [loanId, setLoanId] = useState<string>('')
  const [newRate, setNewRate] = useState('15')
  const [newTerm, setNewTerm] = useState('24')
  const [fee, setFee] = useState('0')

  const { data: loans = [] } = useQuery<LoanCmp[]>({
    queryKey: ['refinance-preview'],
    queryFn: async () => (await api.get('/loans/refinance/preview')).data,
  })

  const calc = useMutation<RefiResp, any, void>({
    mutationFn: async () => (await api.post('/loans/refinance', {
      loan_id: loanId || null,
      new_rate_pct: +newRate || 0,
      new_term_months: +newTerm || 1,
      early_repayment_fee_rub: +fee || 0,
    })).data,
  })

  const r = calc.data

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
            <Repeat className="w-6 h-6 text-purple-500" />
            Рефинансирование
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            Сравни текущие кредиты с потенциальным новым предложением. Считаем аннуитет.
          </p>
        </div>
        <AskAIButton
          context={{ type: 'screen', source_page: 'refinance', source_label: 'Рефинансирование',
            metrics: ['savings_rub', 'breakeven_months', 'recommendation'] }}
          question="Стоит ли рефинансировать кредит при текущих ставках на рынке?"
        />
      </div>

      <Card className="p-4 space-y-3">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Calculator className="w-4 h-4 text-purple-500" /> Параметры нового кредита
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <label className="text-xs text-fg-muted">Какой кредит</label>
            <select value={loanId} onChange={(e) => setLoanId(e.target.value)}
                    className="w-full px-2 py-1 border border-border-subtle rounded text-sm bg-bg">
              <option value="">Все активные ({loans.length})</option>
              {loans.map((l) => (
                <option key={l.loan_id} value={l.loan_id}>
                  {l.lender || 'без названия'} · {formatCurrency(l.current_remaining_principal)} ост.
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-fg-muted">Новая ставка, % годовых</label>
            <input type="number" step="0.1" value={newRate}
                   onChange={(e) => setNewRate(e.target.value)}
                   className="w-full px-2 py-1 border border-border-subtle rounded text-sm bg-bg" />
          </div>
          <div>
            <label className="text-xs text-fg-muted">Срок, мес.</label>
            <input type="number" value={newTerm}
                   onChange={(e) => setNewTerm(e.target.value)}
                   className="w-full px-2 py-1 border border-border-subtle rounded text-sm bg-bg" />
          </div>
          <div>
            <label className="text-xs text-fg-muted">Штраф за досрочку, ₽</label>
            <input type="number" value={fee}
                   onChange={(e) => setFee(e.target.value)}
                   className="w-full px-2 py-1 border border-border-subtle rounded text-sm bg-bg" />
          </div>
        </div>
        <Button onClick={() => calc.mutate()} disabled={calc.isPending || loans.length === 0}>
          {calc.isPending ? 'Считаю…' : 'Рассчитать'}
        </Button>
      </Card>

      {calc.error && (
        <Card className="p-4 text-rose-700 text-sm">
          {(calc.error as any)?.response?.data?.detail || 'Ошибка расчёта'}
        </Card>
      )}

      {r && (
        <>
          {/* Recommendation */}
          <Card className={cn('p-4',
            r.savings_rub > 50000 && 'bg-emerald-50/30 border-emerald-300',
            r.savings_rub <= -50000 && 'bg-rose-50/30 border-rose-300')}>
            <div className="flex items-start gap-3">
              {r.savings_rub > 0
                ? <TrendingDown className="w-6 h-6 text-emerald-600 mt-1" />
                : <TrendingUp className="w-6 h-6 text-rose-600 mt-1" />}
              <div className="flex-1">
                <div className="text-lg font-semibold text-fg">{r.recommendation}</div>
                <div className="text-sm text-fg-muted mt-1">
                  Экономия за весь срок:{' '}
                  <span className={cn('font-semibold tabular-nums',
                    r.savings_rub > 0 ? 'text-emerald-700' : 'text-rose-700')}>
                    {r.savings_rub > 0 ? '+' : ''}{formatCurrency(r.savings_rub)}
                  </span>{' '}
                  ({r.savings_pct > 0 ? '+' : ''}{r.savings_pct.toFixed(1)}%)
                  {r.breakeven_months !== null && (
                    <span className="ml-3">
                      Точка безубытка: <b>{r.breakeven_months} мес.</b>
                    </span>
                  )}
                </div>
              </div>
            </div>
          </Card>

          {/* Side by side comparison */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Card className="p-4">
              <h3 className="text-sm font-semibold text-fg mb-3">Текущие кредиты</h3>
              <dl className="space-y-2 text-sm">
                <Row label="Остаток принципала" value={formatCurrency(r.current_total_remaining)} />
                <Row label="Осталось платить (всего)" value={formatCurrency(r.current_total_payments_left_sum)} bold />
                <Row label="Из них проценты+комиссии" value={formatCurrency(r.current_total_interest_left)} tone="amber" />
              </dl>
            </Card>
            <Card className={cn('p-4', r.savings_rub > 0 && 'border-emerald-300')}>
              <h3 className="text-sm font-semibold text-fg mb-3">Новый кредит</h3>
              <dl className="space-y-2 text-sm">
                <Row label="Тело (с учётом штрафов)" value={formatCurrency(r.new_principal)} />
                <Row label="Ежемесячный платёж" value={formatCurrency(r.new_monthly_payment)} />
                <Row label="Всего к выплате" value={formatCurrency(r.new_total_payments_sum)} bold />
                <Row label="Из них проценты" value={formatCurrency(r.new_total_interest)} tone="amber" />
              </dl>
            </Card>
          </div>

          {/* Detail per loan */}
          <Card className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-fg-muted bg-bg-subtle/30">
                <tr>
                  <th className="py-2 px-3 text-left">Кредит</th>
                  <th className="py-2 px-3 text-right">Ставка</th>
                  <th className="py-2 px-3 text-right">Остаток принципала</th>
                  <th className="py-2 px-3 text-right">Платежей</th>
                  <th className="py-2 px-3 text-right">Сумма платежей</th>
                  <th className="py-2 px-3 text-right">Проценты</th>
                </tr>
              </thead>
              <tbody>
                {r.current.map((l) => (
                  <tr key={l.loan_id} className="border-t border-border-subtle/40">
                    <td className="py-2 px-3">{l.lender || '—'}</td>
                    <td className="py-2 px-3 text-right tabular-nums">{l.current_rate_pct.toFixed(2)}%</td>
                    <td className="py-2 px-3 text-right tabular-nums">{formatCurrency(l.current_remaining_principal)}</td>
                    <td className="py-2 px-3 text-right tabular-nums">{l.current_payments_left}</td>
                    <td className="py-2 px-3 text-right tabular-nums">{formatCurrency(l.current_remaining_payments_sum)}</td>
                    <td className="py-2 px-3 text-right tabular-nums text-amber-700">{formatCurrency(l.current_remaining_interest)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          <Card className="p-3 text-xs text-fg-muted flex items-start gap-2">
            <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            {r.note}
          </Card>
        </>
      )}
    </div>
  )
}

function Row({ label, value, tone, bold }: {
  label: string; value: string; tone?: 'amber'; bold?: boolean
}) {
  return (
    <div className="flex justify-between">
      <dt className="text-fg-muted">{label}</dt>
      <dd className={cn('tabular-nums',
        bold && 'font-semibold',
        tone === 'amber' && 'text-amber-700',
      )}>{value}</dd>
    </div>
  )
}
