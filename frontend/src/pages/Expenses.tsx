import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Wallet, Plus, Trash2, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api } from '@/lib/api'
import { formatCurrency, cn } from '@/lib/utils'
import { DateRangeBar } from '@/components/DateRangeBar'
import { dateParams } from '@/lib/dateParams'

interface ExpenseRow {
  id: string
  date: string
  category: string
  amount: number
  description: string | null
  recurring: boolean
}

const CATEGORY_LABELS: Record<string, string> = {
  salary: 'Зарплата',
  rent: 'Аренда',
  tax: 'Налог',
  software: 'Софт',
  equipment: 'Оборудование',
  legal: 'Юрист',
  other: 'Прочее',
}

const CATEGORY_COLORS: Record<string, string> = {
  salary: 'bg-indigo-50 text-indigo-700',
  rent: 'bg-amber-50 text-amber-700',
  tax: 'bg-rose-50 text-rose-700',
  software: 'bg-violet-50 text-violet-700',
  equipment: 'bg-emerald-50 text-emerald-700',
  legal: 'bg-blue-50 text-blue-700',
  other: 'bg-fg-subtle/10 text-fg-muted',
}

export function Expenses() {
  const qc = useQueryClient()
  const [days, setDays] = useState(90)
  const [dateFrom, setDateFrom] = useState<string | null>(null)
  const [dateTo, setDateTo] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)

  const { data, isLoading } = useQuery<{ rows: ExpenseRow[]; total_amount: number }>({
    queryKey: ['expenses', days, dateFrom, dateTo],
    queryFn: async () => {
      const p = dateParams(days, dateFrom, dateTo)
      return (await api.get(`/finance/expenses/?${p.toString()}`)).data
    },
  })

  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [category, setCategory] = useState('salary')
  const [amount, setAmount] = useState('')
  const [description, setDescription] = useState('')

  const create = useMutation({
    mutationFn: async () => {
      return (await api.post('/finance/expenses/', {
        date, category, amount: parseFloat(amount), description: description || null,
      })).data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['expenses'] })
      setShowForm(false)
      setAmount('')
      setDescription('')
    },
  })

  const del = useMutation({
    mutationFn: async (id: string) => api.delete(`/finance/expenses/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['expenses'] }),
  })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Внутренние расходы</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Зарплаты, аренда, налоги — учитываются в P&L отдельно от Ozon-комиссий.
            Сумма: {formatCurrency(data?.total_amount ?? 0)}
          </p>
        </div>
        <div className="flex gap-2">
          <DateRangeBar days={days} onChange={(r) => { setDays(r.days); setDateFrom(r.dateFrom); setDateTo(r.dateTo) }} />
          <Button onClick={() => setShowForm((v) => !v)}>
            <Plus className="w-4 h-4" /> Расход
          </Button>
        </div>
      </div>

      {showForm && (
        <Card className="p-5">
          <h3 className="text-base font-semibold text-fg mb-4">Новый расход</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Дата</label>
              <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Категория</label>
              <select value={category} onChange={(e) => setCategory(e.target.value)}
                className="h-9 px-3 rounded-md border border-border bg-surface text-sm w-full">
                {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Сумма ₽</label>
              <Input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0" />
            </div>
            <div className="md:col-span-2">
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Описание</label>
              <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="напр. Зарплата Иванов май" />
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="ghost" onClick={() => setShowForm(false)}>Отмена</Button>
            <Button onClick={() => create.mutate()} disabled={create.isPending || !amount}>
              {create.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Сохранить'}
            </Button>
          </div>
        </Card>
      )}

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 flex justify-center text-fg-muted"><Loader2 className="w-5 h-5 animate-spin" /></div>
        ) : (data?.rows.length ?? 0) === 0 ? (
          <div className="py-12 flex flex-col items-center text-fg-muted text-sm">
            <Wallet className="w-8 h-8 mb-2 text-fg-subtle" />
            <p>Расходов пока нет. Добавьте первую.</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-bg-subtle/50 border-b border-border-subtle">
              <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                <th className="py-2.5 px-4 font-medium">дата</th>
                <th className="py-2.5 px-4 font-medium">категория</th>
                <th className="py-2.5 px-4 font-medium">описание</th>
                <th className="py-2.5 px-4 font-medium text-right">сумма</th>
                <th className="py-2.5 px-4 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {data!.rows.map((r) => (
                <tr key={r.id} className="hover:bg-bg-subtle/40">
                  <td className="py-2.5 px-4 text-fg-muted tabular-nums">{r.date}</td>
                  <td className="py-2.5 px-4">
                    <span className={cn('text-xs font-medium px-1.5 py-0.5 rounded', CATEGORY_COLORS[r.category])}>
                      {CATEGORY_LABELS[r.category] ?? r.category}
                    </span>
                  </td>
                  <td className="py-2.5 px-4 text-fg-muted">{r.description || '—'}</td>
                  <td className="py-2.5 px-4 text-right tabular-nums font-mono text-rose-700">
                    −{formatCurrency(r.amount)}
                  </td>
                  <td className="py-2.5 px-2">
                    <button onClick={() => del.mutate(r.id)} className="p-1.5 rounded text-fg-subtle hover:text-rose-700 hover:bg-rose-50">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}
