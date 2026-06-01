import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CreditCard, Loader2, Plus, Trash2, Check, Calendar } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, cn } from '@/lib/utils'

interface LoanRow {
  id: string
  lender: string | null
  principal: number
  rate_pct: number | null
  issued_at: string
  term_months: number | null
  schedule_type: string
  status: string
  note: string | null
  cabinet_id: string | null
  total_principal_paid: number
  total_interest_paid: number
  total_fee_paid: number
  remaining_principal: number
  next_pay_date: string | null
}

interface PaymentRow {
  id: string
  seq: number
  pay_date: string
  principal_part: number
  interest_part: number
  fee_part: number
  is_paid: boolean
  paid_at: string | null
  source: string
  note: string | null
}

interface LoansResponse {
  items: LoanRow[]
  total_active_principal: number
  total_interest_ytd: number
  total_fee_ytd: number
}

interface Cabinet {
  id: string
  name: string
}

const SCHEDULE_LABEL: Record<string, string> = {
  annuity: 'Аннуитет',
  differentiated: 'Дифференцированный',
  manual: 'Ручной',
}

export function Loans() {
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)

  const { data, isLoading } = useQuery<LoansResponse>({
    queryKey: ['loans', 'list'],
    queryFn: async () => (await api.get('/loans')).data,
  })
  const { data: cabinets } = useQuery<Cabinet[]>({
    queryKey: ['ozon-accounts'],
    queryFn: async () => (await api.get('/ozon-accounts/')).data,
  })

  const deleteLoan = useMutation({
    mutationFn: async (id: string) => api.delete(`/loans/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['loans'] }),
  })

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Кредиты</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Настоящие займы от банка (Ozon.Invest и внешние). Тело займа в P&L не идёт —
            только в ДДС. Процент и комиссия — расход в P&L. Через Seller API эти займы
            не отдаются, поэтому вводим вручную.
          </p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-accent text-white rounded-lg text-sm font-medium hover:bg-accent-hover"
        >
          <Plus className="size-4" /> Добавить договор
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Card className="p-5">
          <p className="text-[11px] uppercase text-fg-muted">Остаток тела по активным</p>
          <p className="text-2xl font-semibold text-fg mt-1 tabular-nums">
            {formatCurrency(data?.total_active_principal ?? 0)}
          </p>
        </Card>
        <Card className="p-5">
          <p className="text-[11px] uppercase text-fg-muted">Проценты YTD</p>
          <p className="text-2xl font-semibold text-fg mt-1 tabular-nums">
            {formatCurrency(data?.total_interest_ytd ?? 0)}
          </p>
          <p className="text-[11px] text-fg-muted mt-1">фактически уплачено в P&L</p>
        </Card>
        <Card className="p-5">
          <p className="text-[11px] uppercase text-fg-muted">Комиссии YTD</p>
          <p className="text-2xl font-semibold text-fg mt-1 tabular-nums">
            {formatCurrency(data?.total_fee_ytd ?? 0)}
          </p>
        </Card>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="size-6 animate-spin text-fg-muted" />
        </div>
      ) : !data?.items.length ? (
        <Card className="p-12 text-center">
          <CreditCard className="size-12 mx-auto text-fg-muted/40" />
          <p className="text-fg-muted mt-3">Пока нет ни одного займа</p>
          <p className="text-xs text-fg-muted mt-1">
            Заведи договор — Flowoi построит график платежей и подключит его к P&L и ДДС
          </p>
        </Card>
      ) : (
        <div className="space-y-3">
          {data.items.map((ln) => (
            <Card key={ln.id} className="overflow-hidden">
              <div
                className="p-4 cursor-pointer hover:bg-bg-subtle/40"
                onClick={() => setExpanded(expanded === ln.id ? null : ln.id)}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="text-base font-medium text-fg truncate">
                        {ln.lender || 'Без названия'}
                      </h3>
                      <span
                        className={cn(
                          'px-2 py-0.5 rounded text-[10px] uppercase font-medium',
                          ln.status === 'active'
                            ? 'bg-emerald-50 text-emerald-700'
                            : 'bg-fg-subtle/10 text-fg-muted',
                        )}
                      >
                        {ln.status === 'active' ? 'Активен' : 'Закрыт'}
                      </span>
                    </div>
                    <p className="text-xs text-fg-muted mt-0.5">
                      {SCHEDULE_LABEL[ln.schedule_type]} ·{' '}
                      {ln.rate_pct != null ? `${ln.rate_pct}% годовых` : 'без процента'} ·{' '}
                      {ln.term_months ? `${ln.term_months} мес` : 'без срока'} · с{' '}
                      {ln.issued_at}
                      {ln.cabinet_id && cabinets && (
                        <>
                          {' · '}
                          <span className="text-fg">
                            {cabinets.find((c) => c.id === ln.cabinet_id)?.name ?? '—'}
                          </span>
                        </>
                      )}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-lg font-semibold text-fg tabular-nums">
                      {formatCurrency(ln.remaining_principal)}
                    </p>
                    <p className="text-[11px] text-fg-muted">из {formatCurrency(ln.principal)}</p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      if (confirm(`Удалить договор «${ln.lender || 'без названия'}»?`))
                        deleteLoan.mutate(ln.id)
                    }}
                    className="p-2 text-fg-muted hover:text-rose-600"
                  >
                    <Trash2 className="size-4" />
                  </button>
                </div>
                {ln.next_pay_date && (
                  <p className="text-xs text-amber-700 mt-2 flex items-center gap-1">
                    <Calendar className="size-3" /> Следующий платёж: {ln.next_pay_date}
                  </p>
                )}
              </div>
              {expanded === ln.id && <PaymentsList loanId={ln.id} />}
            </Card>
          ))}
        </div>
      )}

      {showAdd && (
        <AddLoanModal
          cabinets={cabinets || []}
          onClose={() => setShowAdd(false)}
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ['loans'] })
            setShowAdd(false)
          }}
        />
      )}
    </div>
  )
}

// === Список платежей по займу ============================================

function PaymentsList({ loanId }: { loanId: string }) {
  const qc = useQueryClient()
  const [showManual, setShowManual] = useState(false)
  const { data, isLoading } = useQuery<PaymentRow[]>({
    queryKey: ['loans', loanId, 'payments'],
    queryFn: async () => (await api.get(`/loans/${loanId}/payments`)).data,
  })

  const markPaid = useMutation({
    mutationFn: async (seq: number) =>
      api.post(`/loans/${loanId}/payments/${seq}/pay`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['loans'] })
    },
  })

  if (isLoading) {
    return (
      <div className="p-4 border-t border-fg-subtle/15 flex justify-center">
        <Loader2 className="size-4 animate-spin text-fg-muted" />
      </div>
    )
  }

  const header = (
    <div className="border-t border-fg-subtle/15 px-4 py-2 flex justify-between items-center bg-bg-subtle/30">
      <span className="text-xs text-fg-muted">
        {data?.length ? `${data.length} платежей в графике` : 'Нет платежей'}
      </span>
      <button
        onClick={() => setShowManual(true)}
        className="text-xs text-accent hover:underline"
      >
        + Ручной платёж
      </button>
    </div>
  )

  if (!data?.length) {
    return (
      <>
        {header}
        <div className="p-4 text-xs text-fg-muted">
          Нет платежей. Добавь вручную либо пересоздай договор с указанием срока.
        </div>
        {showManual && (
          <ManualPaymentModal
            loanId={loanId}
            onClose={() => setShowManual(false)}
            onCreated={() => {
              qc.invalidateQueries({ queryKey: ['loans'] })
              setShowManual(false)
            }}
          />
        )}
      </>
    )
  }

  return (
    <>
      {header}
      {showManual && (
        <ManualPaymentModal
          loanId={loanId}
          onClose={() => setShowManual(false)}
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ['loans'] })
            setShowManual(false)
          }}
        />
      )}
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[10px] uppercase text-fg-muted bg-bg-subtle/30">
            <th className="px-4 py-2">#</th>
            <th className="px-4 py-2">Дата</th>
            <th className="px-4 py-2 text-right">Тело</th>
            <th className="px-4 py-2 text-right">Процент</th>
            <th className="px-4 py-2 text-right">Комиссия</th>
            <th className="px-4 py-2 text-right">Итого</th>
            <th className="px-4 py-2">Статус</th>
            <th className="px-4 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {data.map((p) => {
            const total = p.principal_part + p.interest_part + p.fee_part
            return (
              <tr key={p.id} className="border-t border-fg-subtle/10">
                <td className="px-4 py-2 text-fg-muted">{p.seq}</td>
                <td className="px-4 py-2 tabular-nums">{p.pay_date}</td>
                <td className="px-4 py-2 text-right tabular-nums">
                  {formatCurrency(p.principal_part)}
                </td>
                <td className="px-4 py-2 text-right tabular-nums">
                  {formatCurrency(p.interest_part)}
                </td>
                <td className="px-4 py-2 text-right tabular-nums">
                  {formatCurrency(p.fee_part)}
                </td>
                <td className="px-4 py-2 text-right font-medium tabular-nums">
                  {formatCurrency(total)}
                </td>
                <td className="px-4 py-2">
                  {p.is_paid ? (
                    <span className="text-emerald-700 text-xs flex items-center gap-1">
                      <Check className="size-3" /> Оплачен{p.paid_at ? ` ${p.paid_at}` : ''}
                    </span>
                  ) : (
                    <span className="text-fg-muted text-xs">В графике</span>
                  )}
                </td>
                <td className="px-4 py-2">
                  {!p.is_paid && (
                    <button
                      onClick={() => markPaid.mutate(p.seq)}
                      className="text-xs text-accent hover:underline"
                    >
                      Отметить оплаченным
                    </button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
    </>
  )
}

// === Модалка ручного платежа ============================================

function ManualPaymentModal({
  loanId,
  onClose,
  onCreated,
}: {
  loanId: string
  onClose: () => void
  onCreated: () => void
}) {
  const [form, setForm] = useState({
    pay_date: new Date().toISOString().slice(0, 10),
    principal_part: '',
    interest_part: '',
    fee_part: '',
    note: '',
  })
  const [error, setError] = useState<string | null>(null)

  const submit = useMutation({
    mutationFn: async () =>
      api.post(`/loans/${loanId}/payments`, {
        pay_date: form.pay_date,
        principal_part: parseFloat(form.principal_part || '0'),
        interest_part: parseFloat(form.interest_part || '0'),
        fee_part: parseFloat(form.fee_part || '0'),
        note: form.note || null,
      }),
    onSuccess: () => onCreated(),
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e?.response?.data?.detail || 'Ошибка'),
  })

  const total =
    (parseFloat(form.principal_part || '0') || 0) +
    (parseFloat(form.interest_part || '0') || 0) +
    (parseFloat(form.fee_part || '0') || 0)

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-bg rounded-xl shadow-xl max-w-md w-full p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-fg mb-1">Ручной платёж</h2>
        <p className="text-xs text-fg-muted mb-4">
          Платёж вне графика. Тело идёт только в ДДС; процент и комиссия — и в ДДС, и в P&L.
        </p>

        <div className="space-y-3">
          <Field label="Дата платежа" value={form.pay_date}
            onChange={(v) => setForm({ ...form, pay_date: v })} type="date" />
          <Field label="Тело (principal), ₽" value={form.principal_part}
            onChange={(v) => setForm({ ...form, principal_part: v })}
            placeholder="0" type="number" />
          <Field label="Процент, ₽" value={form.interest_part}
            onChange={(v) => setForm({ ...form, interest_part: v })}
            placeholder="0" type="number" />
          <Field label="Комиссия, ₽" value={form.fee_part}
            onChange={(v) => setForm({ ...form, fee_part: v })}
            placeholder="0" type="number" />
          <Field label="Заметка" value={form.note}
            onChange={(v) => setForm({ ...form, note: v })}
            placeholder="Назначение, дата платёжки…" />
        </div>

        <div className="mt-3 p-3 bg-bg-subtle/40 rounded text-xs">
          <div className="flex justify-between">
            <span className="text-fg-muted">Итого к оплате:</span>
            <b className="tabular-nums">{total.toLocaleString('ru-RU')} ₽</b>
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-fg-muted">Из них в P&L (% + комиссия):</span>
            <b className="tabular-nums">
              {(
                (parseFloat(form.interest_part || '0') || 0) +
                (parseFloat(form.fee_part || '0') || 0)
              ).toLocaleString('ru-RU')}{' '}
              ₽
            </b>
          </div>
        </div>

        {error && <p className="text-sm text-rose-600 mt-3">{error}</p>}

        <div className="flex gap-2 mt-5 justify-end">
          <button onClick={onClose}
            className="px-4 py-2 text-sm border border-fg-subtle/30 rounded-lg hover:bg-bg-subtle/30">
            Отмена
          </button>
          <button onClick={() => submit.mutate()}
            disabled={total <= 0 || submit.isPending}
            className="px-4 py-2 bg-accent text-white text-sm rounded-lg hover:bg-accent-hover disabled:opacity-50">
            {submit.isPending ? 'Сохраняю…' : 'Внести платёж'}
          </button>
        </div>
      </div>
    </div>
  )
}

// === Модалка добавления займа ============================================

function AddLoanModal({
  cabinets,
  onClose,
  onCreated,
}: {
  cabinets: Cabinet[]
  onClose: () => void
  onCreated: () => void
}) {
  const [form, setForm] = useState({
    lender: '',
    principal: '',
    rate_pct: '',
    issued_at: new Date().toISOString().slice(0, 10),
    term_months: '12',
    schedule_type: 'annuity',
    cabinet_id: '',
    note: '',
  })
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        lender: form.lender || null,
        principal: parseFloat(form.principal),
        issued_at: form.issued_at,
        schedule_type: form.schedule_type,
        note: form.note || null,
      }
      if (form.rate_pct) payload.rate_pct = parseFloat(form.rate_pct)
      if (form.term_months) payload.term_months = parseInt(form.term_months)
      if (form.cabinet_id) payload.cabinet_id = form.cabinet_id
      return api.post('/loans', payload)
    },
    onSuccess: () => onCreated(),
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e?.response?.data?.detail || 'Ошибка'),
  })

  const update = (k: keyof typeof form, v: string) =>
    setForm((f) => ({ ...f, [k]: v }))

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-bg rounded-xl shadow-xl max-w-lg w-full p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-xl font-semibold text-fg mb-4">Новый кредит</h2>

        <div className="space-y-3">
          <Field label="Банк / партнёр" value={form.lender}
            onChange={(v) => update('lender', v)} placeholder="Например: Тинькофф Бизнес" />
          <Field label="Сумма займа (тело), ₽" value={form.principal}
            onChange={(v) => update('principal', v)} placeholder="1000000" type="number" />
          <div className="grid grid-cols-2 gap-3">
            <Field label="Ставка, % годовых" value={form.rate_pct}
              onChange={(v) => update('rate_pct', v)} placeholder="22.5" type="number" />
            <Field label="Срок, мес" value={form.term_months}
              onChange={(v) => update('term_months', v)} placeholder="12" type="number" />
          </div>
          <Field label="Дата выдачи" value={form.issued_at}
            onChange={(v) => update('issued_at', v)} type="date" />
          <div>
            <label className="text-xs text-fg-muted block mb-1">Тип графика</label>
            <select
              value={form.schedule_type}
              onChange={(e) => update('schedule_type', e.target.value)}
              className="w-full px-3 py-2 border border-fg-subtle/30 rounded-lg text-sm bg-bg"
            >
              <option value="annuity">Аннуитет — равные платежи</option>
              <option value="differentiated">Дифференцированный — убывающие</option>
              <option value="manual">Ручной — внесу платежи сам</option>
            </select>
          </div>
          {cabinets.length > 0 && (
            <div>
              <label className="text-xs text-fg-muted block mb-1">
                Привязать к кабинету (опционально)
              </label>
              <select
                value={form.cabinet_id}
                onChange={(e) => update('cabinet_id', e.target.value)}
                className="w-full px-3 py-2 border border-fg-subtle/30 rounded-lg text-sm bg-bg"
              >
                <option value="">— Общий заём, без привязки —</option>
                {cabinets.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <Field label="Заметка" value={form.note}
            onChange={(v) => update('note', v)} placeholder="Назначение, реквизиты договора…" />
        </div>

        {error && (
          <p className="text-sm text-rose-600 mt-3">{error}</p>
        )}

        <div className="flex gap-2 mt-5 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm border border-fg-subtle/30 rounded-lg hover:bg-bg-subtle/30"
          >
            Отмена
          </button>
          <button
            onClick={() => create.mutate()}
            disabled={!form.principal || create.isPending}
            className="px-4 py-2 bg-accent text-white text-sm rounded-lg hover:bg-accent-hover disabled:opacity-50"
          >
            {create.isPending ? 'Сохраняю…' : 'Создать договор'}
          </button>
        </div>
      </div>
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  type?: string
}) {
  return (
    <div>
      <label className="text-xs text-fg-muted block mb-1">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2 border border-fg-subtle/30 rounded-lg text-sm bg-bg"
      />
    </div>
  )
}
