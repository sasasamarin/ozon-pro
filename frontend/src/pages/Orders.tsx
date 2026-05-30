import { useState } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { ShoppingBag, Search, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { OrdersDailyChart } from '@/components/OrdersDailyChart'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'

interface OrderItem {
  product_id: string | null
  offer_id: string | null
  name: string | null
  quantity: number
  price: number
  total_price: number
}

interface OrderRow {
  id: string
  posting_number: string
  order_number: string | null
  order_type: string
  status: string
  cabinet_id: string
  cabinet_name: string
  total_amount: number
  commission_amount: number
  delivery_price: number
  cluster_to: string | null
  order_created_at: string | null
  delivered_at: string | null
  items: OrderItem[]
}

interface OrdersResponse {
  page: number
  page_size: number
  total: number
  items: OrderRow[]
}

const STATUS_LABEL: Record<string, { label: string; tone: 'good' | 'neutral' | 'bad' | 'warn' }> = {
  delivered: { label: 'Доставлено', tone: 'good' },
  delivering: { label: 'В пути', tone: 'neutral' },
  cancelled: { label: 'Отменён', tone: 'bad' },
  not_accepted: { label: 'Не принят', tone: 'bad' },
  awaiting_packaging: { label: 'Сборка', tone: 'warn' },
  awaiting_deliver: { label: 'К отгрузке', tone: 'warn' },
  arbitration: { label: 'Арбитраж', tone: 'warn' },
}

function StatusBadge({ status }: { status: string }) {
  const meta = STATUS_LABEL[status] || { label: status, tone: 'neutral' as const }
  return (
    <span
      className={cn(
        'text-[11px] font-medium px-2 py-0.5 rounded-full inline-block',
        meta.tone === 'good' && 'text-emerald-700 bg-emerald-50',
        meta.tone === 'bad' && 'text-rose-700 bg-rose-50',
        meta.tone === 'warn' && 'text-amber-700 bg-amber-50',
        meta.tone === 'neutral' && 'text-fg-muted bg-bg-subtle',
      )}
    >
      {meta.label}
    </span>
  )
}

const PAGE_SIZE = 50

export function Orders() {
  const { selectedCabinetIds } = useCabinetStore()
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<string>('')
  const [search, setSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const { data, isLoading, isFetching } = useQuery<OrdersResponse>({
    queryKey: ['orders', page, status, search, dateFrom, dateTo, selectedCabinetIds],
    queryFn: async () => {
      const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) })
      selectedCabinetIds.forEach((id) => params.append('cabinet_ids', id))
      if (status) params.append('status', status)
      if (search) params.append('search', search)
      if (dateFrom) params.append('date_from', dateFrom)
      if (dateTo) params.append('date_to', dateTo)
      const res = await api.get(`/orders/?${params.toString()}`)
      return res.data
    },
    placeholderData: keepPreviousData,
  })

  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const startIdx = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const endIdx = Math.min(total, page * PAGE_SIZE)

  const resetFilters = () => {
    setStatus('')
    setSearch('')
    setDateFrom('')
    setDateTo('')
    setPage(1)
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Заказы</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          {formatNumber(total)} {total === 1 ? 'заказ' : 'заказов'} в выбранных кабинетах
        </p>
      </div>

      <OrdersDailyChart cabinetIds={selectedCabinetIds} />

      {/* Filters */}
      <Card className="p-4 flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[240px]">
          <label className="block text-[11px] font-medium text-fg-muted uppercase tracking-wider mb-1">
            Поиск
          </label>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-fg-subtle" />
            <Input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
              placeholder="posting / order / offer_id"
              className="pl-9"
            />
          </div>
        </div>
        <div>
          <label className="block text-[11px] font-medium text-fg-muted uppercase tracking-wider mb-1">
            Статус
          </label>
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value)
              setPage(1)
            }}
            className="h-9 px-3 rounded-md border border-border bg-surface text-sm"
          >
            <option value="">все</option>
            {Object.entries(STATUS_LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-[11px] font-medium text-fg-muted uppercase tracking-wider mb-1">
            От
          </label>
          <Input
            type="date"
            value={dateFrom}
            onChange={(e) => {
              setDateFrom(e.target.value)
              setPage(1)
            }}
            className="w-[150px]"
          />
        </div>
        <div>
          <label className="block text-[11px] font-medium text-fg-muted uppercase tracking-wider mb-1">
            До
          </label>
          <Input
            type="date"
            value={dateTo}
            onChange={(e) => {
              setDateTo(e.target.value)
              setPage(1)
            }}
            className="w-[150px]"
          />
        </div>
        {(status || search || dateFrom || dateTo) && (
          <Button variant="ghost" onClick={resetFilters}>
            Сбросить
          </Button>
        )}
      </Card>

      {/* Table */}
      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 flex justify-center items-center text-fg-muted">
            <Loader2 className="w-5 h-5 animate-spin mr-2" />
            Загрузка…
          </div>
        ) : total === 0 ? (
          <div className="py-20 flex flex-col items-center text-fg-muted">
            <ShoppingBag className="w-8 h-8 mb-3 text-fg-subtle" />
            <p className="text-sm">Заказы не найдены</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                  <th className="py-2.5 px-4 font-medium">posting</th>
                  <th className="py-2.5 px-4 font-medium">дата</th>
                  <th className="py-2.5 px-4 font-medium">кабинет</th>
                  <th className="py-2.5 px-4 font-medium">тип</th>
                  <th className="py-2.5 px-4 font-medium">статус</th>
                  <th className="py-2.5 px-4 font-medium">товары</th>
                  <th className="py-2.5 px-4 font-medium text-right">сумма</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {(data?.items || []).map((o) => {
                  const expanded = expandedId === o.id
                  const dt = o.order_created_at
                    ? new Date(o.order_created_at).toLocaleDateString('ru-RU', {
                        day: '2-digit',
                        month: '2-digit',
                        year: '2-digit',
                      })
                    : '—'
                  return (
                    <>
                      <tr
                        key={o.id}
                        onClick={() => setExpandedId(expanded ? null : o.id)}
                        className={cn(
                          'cursor-pointer hover:bg-bg-subtle/50',
                          expanded && 'bg-bg-subtle/60',
                        )}
                      >
                        <td className="py-2.5 px-4 font-mono text-xs text-fg">
                          {o.posting_number}
                        </td>
                        <td className="py-2.5 px-4 text-fg-muted tabular-nums">{dt}</td>
                        <td className="py-2.5 px-4 text-fg">{o.cabinet_name}</td>
                        <td className="py-2.5 px-4 uppercase text-xs text-fg-muted">
                          {o.order_type}
                        </td>
                        <td className="py-2.5 px-4">
                          <StatusBadge status={o.status} />
                        </td>
                        <td className="py-2.5 px-4 text-fg-muted truncate max-w-[280px]">
                          {o.items.length === 1
                            ? o.items[0].name || o.items[0].offer_id
                            : `${o.items.length} позиции`}
                        </td>
                        <td className="py-2.5 px-4 text-right tabular-nums font-mono text-fg">
                          {formatCurrency(o.total_amount)}
                        </td>
                      </tr>
                      {expanded && (
                        <tr className="bg-bg-subtle/40">
                          <td colSpan={7} className="px-4 py-3">
                            <div className="flex flex-col gap-2">
                              {o.items.map((it, i) => (
                                <div
                                  key={i}
                                  className="flex items-center justify-between gap-3 text-xs"
                                >
                                  <div className="flex-1 min-w-0">
                                    <div className="font-medium text-fg truncate">
                                      {it.name || '—'}
                                    </div>
                                    <div className="text-fg-subtle font-mono">
                                      {it.offer_id || '—'}
                                    </div>
                                  </div>
                                  <span className="text-fg-muted tabular-nums">
                                    {formatNumber(it.quantity)} × {formatCurrency(it.price)}
                                  </span>
                                  <span className="text-fg font-mono tabular-nums w-24 text-right">
                                    {formatCurrency(it.total_price)}
                                  </span>
                                </div>
                              ))}
                              <div className="flex justify-between pt-2 mt-1 border-t border-border-subtle text-xs text-fg-muted">
                                <span>комиссия: {formatCurrency(o.commission_amount)}</span>
                                <span>доставка: {formatCurrency(o.delivery_price)}</span>
                                {o.cluster_to && <span>кластер: {o.cluster_to}</span>}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {total > 0 && (
          <div className="px-4 py-3 border-t border-border-subtle flex items-center justify-between text-xs text-fg-muted">
            <span>
              {formatNumber(startIdx)}–{formatNumber(endIdx)} из {formatNumber(total)}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page <= 1}
                className="!h-8 !px-2"
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="tabular-nums">
                {page} / {totalPages}
                {isFetching && (
                  <Loader2 className="inline-block w-3 h-3 ml-2 animate-spin" />
                )}
              </span>
              <Button
                variant="ghost"
                onClick={() => setPage(Math.min(totalPages, page + 1))}
                disabled={page >= totalPages}
                className="!h-8 !px-2"
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
