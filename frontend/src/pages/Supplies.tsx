import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Truck, Plus, Loader2, Trash2, ExternalLink } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, cn } from '@/lib/utils'

type SupplyStatus = 'ordered' | 'in_transit' | 'arrived'
type DateField = 'payment_date' | 'dispatch_date' | 'actual_departure_date' | 'supply_date'
type TransportType = 'rzd' | 'auto' | 'auto_consolidated' | 'cargo' | 'sea'

interface SupplyListRow {
  id: string; name: string; tag: string | null
  transport_type: TransportType | null
  route: string | null
  status: SupplyStatus
  payment_date: string | null
  dispatch_date: string | null
  dispatch_from: string | null
  actual_departure_date: string | null
  supply_date: string | null
  items_count: number
  items_total: number
  costs_sum: number
  grand_total: number
  docs_count: number
}

const STATUS_META: Record<SupplyStatus, { label: string; cls: string }> = {
  ordered:    { label: 'Заказана', cls: 'bg-fg-subtle/15 text-fg-muted' },
  in_transit: { label: 'В пути',   cls: 'bg-amber-100 text-amber-800' },
  arrived:    { label: 'Получена', cls: 'bg-emerald-100 text-emerald-800' },
}

export const TRANSPORT_META: Record<TransportType, string> = {
  rzd:                'РЖД',
  auto:               'Авто',
  auto_consolidated:  'Авто-сборный',
  cargo:              'Карго',
  sea:                'Море',
}

export function Supplies() {
  const qc = useQueryClient()
  const navigate = useNavigate()

  const [search, setSearch] = useState('')
  const [filterStatus, setFilterStatus] = useState<SupplyStatus | ''>('')
  const [dateField, setDateField] = useState<DateField>('supply_date')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const { data: list, isLoading } = useQuery<SupplyListRow[]>({
    queryKey: ['supplies', 'list', search, filterStatus, dateField, dateFrom, dateTo],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (search) params.set('search', search)
      if (filterStatus) params.set('status', filterStatus)
      if (dateFrom || dateTo) {
        params.set('date_field', dateField)
        if (dateFrom) params.set('date_from', dateFrom)
        if (dateTo) params.set('date_to', dateTo)
      }
      const qs = params.toString()
      return (await api.get(`/supplies${qs ? '?' + qs : ''}`)).data
    },
  })

  const del = useMutation({
    mutationFn: async (id: string) => api.delete(`/supplies/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['supplies'] }),
  })

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Поставки</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Ручной ввод поставок (машина/вагон) с SKU, затратами и документами.
          </p>
        </div>
        <button
          onClick={() => navigate('/procurement/supplies/new')}
          className="inline-flex items-center gap-2 px-4 py-2 bg-accent text-white rounded-lg text-sm font-medium hover:bg-accent-hover"
        >
          <Plus className="size-4" /> Поставка
        </button>
      </div>

      {/* Фильтры */}
      <Card className="p-3">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-2 items-end">
          <div className="md:col-span-3">
            <label className="text-[10px] text-fg-muted uppercase block mb-1">Поиск по названию</label>
            <input value={search} onChange={(e) => setSearch(e.target.value)}
                   placeholder="название…"
                   className="w-full px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg" />
          </div>
          <div className="md:col-span-2">
            <label className="text-[10px] text-fg-muted uppercase block mb-1">Статус</label>
            <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value as any)}
                    className="w-full px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg">
              <option value="">все</option>
              <option value="ordered">Заказана</option>
              <option value="in_transit">В пути</option>
              <option value="arrived">Получена</option>
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="text-[10px] text-fg-muted uppercase block mb-1">Фильтр по дате</label>
            <select value={dateField} onChange={(e) => setDateField(e.target.value as DateField)}
                    className="w-full px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg">
              <option value="supply_date">Приход</option>
              <option value="payment_date">Оплата</option>
              <option value="dispatch_date">Отправка</option>
              <option value="actual_departure_date">Факт. выход</option>
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="text-[10px] text-fg-muted uppercase block mb-1">От</label>
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
                   className="w-full px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg" />
          </div>
          <div className="md:col-span-2">
            <label className="text-[10px] text-fg-muted uppercase block mb-1">До</label>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
                   className="w-full px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg" />
          </div>
          <div className="md:col-span-1">
            {(search || filterStatus || dateFrom || dateTo) && (
              <button onClick={() => { setSearch(''); setFilterStatus(''); setDateFrom(''); setDateTo('') }}
                      className="text-xs text-fg-muted hover:text-fg">сброс</button>
            )}
          </div>
        </div>
      </Card>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="size-6 animate-spin text-fg-muted" />
        </div>
      ) : !list?.length ? (
        <Card className="p-12 text-center">
          <Truck className="size-12 mx-auto text-fg-muted/40" />
          <p className="text-fg-muted mt-3">Поставок не найдено</p>
        </Card>
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] uppercase text-fg-muted bg-bg-subtle/40">
                <th className="px-3 py-2.5">Название</th>
                <th className="px-3 py-2.5">Тэг</th>
                <th className="px-3 py-2.5">Тип</th>
                <th className="px-3 py-2.5">Статус</th>
                <th className="px-3 py-2.5">Оплата</th>
                <th className="px-3 py-2.5">Отправка</th>
                <th className="px-3 py-2.5">Факт. выход</th>
                <th className="px-3 py-2.5">Приход</th>
                <th className="px-3 py-2.5 text-right">SKU</th>
                <th className="px-3 py-2.5 text-right">Σ товары</th>
                <th className="px-3 py-2.5 text-right">Σ затрат</th>
                <th className="px-3 py-2.5 text-right">ИТОГО</th>
                <th className="px-3 py-2.5 text-center">📎</th>
                <th className="px-3 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {list.map(s => (
                <tr key={s.id} className="border-t border-fg-subtle/10 hover:bg-bg-subtle/30">
                  <td className="px-3 py-2.5 font-medium">
                    <Link to={`/procurement/supplies/${s.id}`} className="hover:text-accent">{s.name}</Link>
                    {s.route && <div className="text-[10px] text-fg-muted mt-0.5">{s.route}</div>}
                  </td>
                  <td className="px-3 py-2.5 text-xs">
                    {s.tag && <span className="px-1.5 py-0.5 bg-indigo-50 text-indigo-700 rounded text-[10px]">{s.tag}</span>}
                  </td>
                  <td className="px-3 py-2.5 text-xs">
                    {s.transport_type ? TRANSPORT_META[s.transport_type] : '—'}
                  </td>
                  <td className="px-3 py-2.5">
                    <span className={cn('text-[10px] uppercase px-2 py-0.5 rounded font-medium', STATUS_META[s.status].cls)}>
                      {STATUS_META[s.status].label}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 tabular-nums text-xs">{s.payment_date ?? '—'}</td>
                  <td className="px-3 py-2.5 tabular-nums text-xs">
                    {s.dispatch_date ?? '—'}
                    {s.dispatch_from && <span className="block text-[10px] text-fg-muted">{s.dispatch_from}</span>}
                  </td>
                  <td className="px-3 py-2.5 tabular-nums text-xs">{s.actual_departure_date ?? '—'}</td>
                  <td className="px-3 py-2.5 tabular-nums text-xs">{s.supply_date ?? '—'}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{s.items_count}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{formatCurrency(s.items_total)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{formatCurrency(s.costs_sum)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums font-semibold">{formatCurrency(s.grand_total)}</td>
                  <td className="px-3 py-2.5 text-center text-fg-muted">{s.docs_count || ''}</td>
                  <td className="px-3 py-2.5 text-right whitespace-nowrap">
                    <Link to={`/procurement/supplies/${s.id}`}
                          className="inline-flex items-center gap-1 px-3 py-1.5 bg-accent text-white rounded text-xs font-medium hover:bg-accent-hover">
                      <ExternalLink className="size-3" /> Открыть
                    </Link>
                    <button onClick={() => { if (confirm(`Удалить «${s.name}»?`)) del.mutate(s.id) }}
                            className="ml-2 text-fg-muted hover:text-rose-600 align-middle">
                      <Trash2 className="size-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
