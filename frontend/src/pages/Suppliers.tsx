/**
 * /procurement/suppliers — CRUD поставщиков.
 *
 * Заказы создаются на /procurement (страница SupplierOrders), здесь — справочник.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Building2, Plus, Pencil, Trash2, X, Check } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { AskAIButton } from '@/components/AskAIButton'
import { api } from '@/lib/api'
import { formatCurrency } from '@/lib/utils'

const toast = {
  success: (msg: string) => console.log(msg),
  error: (msg: string) => alert(msg),
}

interface SupplierRow {
  id: string
  name: string
  contact: string | null
  lead_time_days: number | null
  payment_terms: string | null
  orders_count: number
  total_spent_rub: number
  last_order_date: string | null
}

type FormState = {
  id?: string
  name: string
  contact: string
  lead_time_days: string
  payment_terms: string
}

const EMPTY: FormState = { name: '', contact: '', lead_time_days: '', payment_terms: '' }

export function Suppliers() {
  const qc = useQueryClient()
  const [form, setForm] = useState<FormState | null>(null)

  const { data: rows = [] } = useQuery<SupplierRow[]>({
    queryKey: ['suppliers'],
    queryFn: async () => (await api.get('/procurement/orders/suppliers')).data,
  })

  const create = useMutation({
    mutationFn: async (p: any) => (await api.post('/procurement/orders/suppliers', p)).data,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['suppliers'] }); setForm(null); toast.success('Поставщик добавлен') },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Ошибка'),
  })
  const update = useMutation({
    mutationFn: async ({ id, ...p }: any) => (await api.patch(`/procurement/orders/suppliers/${id}`, p)).data,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['suppliers'] }); setForm(null); toast.success('Обновлено') },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Ошибка'),
  })
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/procurement/orders/suppliers/${id}`)).data,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['suppliers'] }); toast.success('Удалено') },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Ошибка удаления'),
  })

  function submit() {
    if (!form) return
    if (!form.name.trim()) return toast.error('Укажите название')
    const payload = {
      name: form.name.trim(),
      contact: form.contact.trim() || null,
      payment_terms: form.payment_terms.trim() || null,
      lead_time_days: form.lead_time_days ? +form.lead_time_days : null,
    }
    if (form.id) update.mutate({ id: form.id, ...payload })
    else create.mutate(payload)
  }

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
            <Building2 className="w-6 h-6 text-blue-500" />
            Поставщики
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            Справочник партнёров. К каждому привязываются заказы на /procurement,
            из них считается себестоимость в продуктах.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => setForm(EMPTY)} className="inline-flex items-center gap-1">
            <Plus className="w-4 h-4" /> Добавить
          </Button>
          <AskAIButton
            context={{
              type: 'screen', source_page: 'suppliers', source_label: 'Поставщики',
              metrics: ['orders_count', 'total_spent_rub', 'lead_time_days'],
            }}
            question="Кто из поставщиков самый дорогой / самый долгий по lead-time?"
          />
        </div>
      </div>

      {form && (
        <Card className="p-4 border-2 border-blue-300 bg-blue-50/30">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div>
              <label className="text-xs text-fg-muted">Название*</label>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full px-2 py-1 border border-border-subtle rounded text-sm bg-bg"
                placeholder="ООО Поставщик"
                autoFocus
              />
            </div>
            <div>
              <label className="text-xs text-fg-muted">Контакт</label>
              <input
                value={form.contact}
                onChange={(e) => setForm({ ...form, contact: e.target.value })}
                className="w-full px-2 py-1 border border-border-subtle rounded text-sm bg-bg"
                placeholder="email / телефон / TG"
              />
            </div>
            <div>
              <label className="text-xs text-fg-muted">Lead-time (дней)</label>
              <input
                type="number" min={0}
                value={form.lead_time_days}
                onChange={(e) => setForm({ ...form, lead_time_days: e.target.value })}
                className="w-full px-2 py-1 border border-border-subtle rounded text-sm bg-bg"
                placeholder="14"
              />
            </div>
            <div>
              <label className="text-xs text-fg-muted">Условия оплаты</label>
              <input
                value={form.payment_terms}
                onChange={(e) => setForm({ ...form, payment_terms: e.target.value })}
                className="w-full px-2 py-1 border border-border-subtle rounded text-sm bg-bg"
                placeholder="50% предоплата"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-3">
            <Button variant="secondary" onClick={() => setForm(null)} className="inline-flex items-center gap-1">
              <X className="w-4 h-4" /> Отмена
            </Button>
            <Button onClick={submit} disabled={create.isPending || update.isPending}
                    className="inline-flex items-center gap-1">
              <Check className="w-4 h-4" /> {form.id ? 'Сохранить' : 'Создать'}
            </Button>
          </div>
        </Card>
      )}

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-fg-muted bg-bg-subtle/30">
            <tr>
              <th className="py-2 px-3 text-left">Название</th>
              <th className="py-2 px-3 text-left">Контакт</th>
              <th className="py-2 px-3 text-right">Lead-time</th>
              <th className="py-2 px-3 text-left">Оплата</th>
              <th className="py-2 px-3 text-right">Заказов</th>
              <th className="py-2 px-3 text-right">Потрачено</th>
              <th className="py-2 px-3 text-left">Последний заказ</th>
              <th className="py-2 px-3 text-right w-24"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id} className="border-t border-border-subtle/40 hover:bg-bg-subtle/20">
                <td className="py-2 px-3 font-medium">{s.name}</td>
                <td className="py-2 px-3 text-fg-muted">{s.contact || '—'}</td>
                <td className="py-2 px-3 text-right tabular-nums">{s.lead_time_days ?? '—'}</td>
                <td className="py-2 px-3 text-fg-muted text-xs">{s.payment_terms || '—'}</td>
                <td className="py-2 px-3 text-right tabular-nums">{s.orders_count}</td>
                <td className="py-2 px-3 text-right tabular-nums">{formatCurrency(s.total_spent_rub)}</td>
                <td className="py-2 px-3 text-xs text-fg-muted">{s.last_order_date || '—'}</td>
                <td className="py-2 px-3 text-right">
                  <div className="inline-flex gap-1">
                    <button onClick={() => setForm({
                      id: s.id, name: s.name, contact: s.contact || '',
                      lead_time_days: s.lead_time_days?.toString() || '',
                      payment_terms: s.payment_terms || '',
                    })} className="p-1 hover:bg-bg-subtle rounded" title="Редактировать">
                      <Pencil className="w-3.5 h-3.5 text-fg-muted" />
                    </button>
                    <button onClick={() => {
                      if (confirm(`Удалить поставщика «${s.name}»?`)) remove.mutate(s.id)
                    }} className="p-1 hover:bg-rose-100 rounded" title="Удалить">
                      <Trash2 className="w-3.5 h-3.5 text-rose-600" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={8} className="py-8 text-center text-fg-muted">
                Поставщиков нет. Добавьте первого, чтобы привязывать заказы.
              </td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
