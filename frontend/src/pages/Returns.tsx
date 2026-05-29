import { useState } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import {
  RotateCcw,
  Search,
  Loader2,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'

interface ReturnRow {
  id: string
  kind: 'return' | 'cancellation'
  cabinet_id: string
  cabinet_name: string
  posting_number: string | null
  product_id: string | null
  product_name: string | null
  offer_id: string | null
  ozon_sku: number | null
  quantity: number
  amount: number | null
  reason: string | null
  status: string | null
  occurred_at: string | null
}

interface ListResp {
  page: number
  page_size: number
  total: number
  total_amount: number
  items: ReturnRow[]
}

interface ReasonRow {
  reason: string
  count: number
  total_amount: number
}

interface StatsResp {
  returns_count: number
  cancellations_count: number
  returns_amount: number
  top_reasons_returns: ReasonRow[]
  top_reasons_cancellations: ReasonRow[]
}

const PAGE_SIZE = 50

type Kind = 'all' | 'returns' | 'cancellations'

export function Returns() {
  const { selectedCabinetIds } = useCabinetStore()
  const [kind, setKind] = useState<Kind>('all')
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const { data, isLoading, isFetching } = useQuery<ListResp>({
    queryKey: ['returns', 'list', kind, page, search, dateFrom, dateTo, selectedCabinetIds],
    queryFn: async () => {
      const p = new URLSearchParams({
        kind, page: String(page), page_size: String(PAGE_SIZE),
      })
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      if (search) p.append('search', search)
      if (dateFrom) p.append('date_from', dateFrom)
      if (dateTo) p.append('date_to', dateTo)
      const res = await api.get(`/returns/?${p.toString()}`)
      return res.data
    },
    placeholderData: keepPreviousData,
  })

  const { data: stats } = useQuery<StatsResp>({
    queryKey: ['returns', 'stats', selectedCabinetIds],
    queryFn: async () => {
      const p = new URLSearchParams({ days: '90' })
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      const res = await api.get(`/returns/stats?${p.toString()}`)
      return res.data
    },
  })

  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const startIdx = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const endIdx = Math.min(total, page * PAGE_SIZE)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Возвраты и отмены</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          Всего {formatNumber(total)} событий · сумма возвратов: {formatCurrency(data?.total_amount ?? 0)}
        </p>
      </div>

      {/* Stats */}
      {stats && (stats.returns_count > 0 || stats.cancellations_count > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card className="p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-fg">Причины возвратов (90 дней)</h3>
              <span className="text-xs text-fg-muted">{stats.returns_count} событий</span>
            </div>
            {stats.top_reasons_returns.length === 0 ? (
              <p className="text-xs text-fg-muted">Нет данных</p>
            ) : (
              <ul className="flex flex-col gap-1.5 text-sm">
                {stats.top_reasons_returns.slice(0, 5).map((r) => (
                  <li key={r.reason} className="flex justify-between text-fg-muted">
                    <span className="truncate max-w-[60%]">{r.reason}</span>
                    <span className="tabular-nums">{r.count}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card className="p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-fg">Причины отмен (90 дней)</h3>
              <span className="text-xs text-fg-muted">{stats.cancellations_count} событий</span>
            </div>
            {stats.top_reasons_cancellations.length === 0 ? (
              <p className="text-xs text-fg-muted">Нет данных</p>
            ) : (
              <ul className="flex flex-col gap-1.5 text-sm">
                {stats.top_reasons_cancellations.slice(0, 5).map((r) => (
                  <li key={r.reason} className="flex justify-between text-fg-muted">
                    <span className="truncate max-w-[60%]">{r.reason}</span>
                    <span className="tabular-nums">{r.count}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}

      {/* Filters */}
      <Card className="p-4 flex flex-wrap items-end gap-3">
        <div className="flex gap-2">
          {(['all', 'returns', 'cancellations'] as Kind[]).map((k) => (
            <button
              key={k}
              onClick={() => { setKind(k); setPage(1) }}
              className={cn(
                'px-3 py-1.5 rounded-md text-sm border transition-colors',
                kind === k
                  ? 'border-fg bg-fg text-bg'
                  : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
              )}
            >
              {k === 'all' && 'Все'}
              {k === 'returns' && 'Возвраты'}
              {k === 'cancellations' && 'Отмены'}
            </button>
          ))}
        </div>
        <div className="flex-1 min-w-[220px]">
          <label className="block text-[11px] font-medium text-fg-muted uppercase tracking-wider mb-1">Поиск</label>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-fg-subtle" />
            <Input
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1) }}
              placeholder="posting / причина"
              className="pl-9"
            />
          </div>
        </div>
        <div>
          <label className="block text-[11px] font-medium text-fg-muted uppercase tracking-wider mb-1">От</label>
          <Input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1) }} className="w-[150px]" />
        </div>
        <div>
          <label className="block text-[11px] font-medium text-fg-muted uppercase tracking-wider mb-1">До</label>
          <Input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1) }} className="w-[150px]" />
        </div>
      </Card>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 flex justify-center items-center text-fg-muted">
            <Loader2 className="w-5 h-5 animate-spin mr-2" /> Загрузка…
          </div>
        ) : total === 0 ? (
          <div className="py-20 flex flex-col items-center text-fg-muted">
            <RotateCcw className="w-8 h-8 mb-3 text-fg-subtle" />
            <p className="text-sm">Возвраты не найдены</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                  <th className="py-2.5 px-4 font-medium">дата</th>
                  <th className="py-2.5 px-4 font-medium">тип</th>
                  <th className="py-2.5 px-4 font-medium">posting</th>
                  <th className="py-2.5 px-4 font-medium">товар</th>
                  <th className="py-2.5 px-4 font-medium">причина</th>
                  <th className="py-2.5 px-4 font-medium text-right">кол-во</th>
                  <th className="py-2.5 px-4 font-medium text-right">сумма</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {(data?.items || []).map((r) => {
                  const dt = r.occurred_at
                    ? new Date(r.occurred_at).toLocaleDateString('ru-RU', {
                        day: '2-digit', month: '2-digit', year: '2-digit',
                      })
                    : '—'
                  return (
                    <tr key={`${r.kind}-${r.id}`} className="hover:bg-bg-subtle/40">
                      <td className="py-2.5 px-4 text-fg-muted tabular-nums whitespace-nowrap">{dt}</td>
                      <td className="py-2.5 px-4">
                        <span className={cn(
                          'text-[11px] font-medium px-1.5 py-0.5 rounded',
                          r.kind === 'return'
                            ? 'bg-rose-50 text-rose-700'
                            : 'bg-amber-50 text-amber-700',
                        )}>
                          {r.kind === 'return' ? 'возврат' : 'отмена'}
                        </span>
                      </td>
                      <td className="py-2.5 px-4 font-mono text-xs text-fg-muted">{r.posting_number || '—'}</td>
                      <td className="py-2.5 px-4">
                        <div className="min-w-0">
                          <div className="text-fg truncate max-w-[260px]">{r.product_name || '—'}</div>
                          <div className="text-xs text-fg-muted font-mono truncate">{r.offer_id || (r.ozon_sku ? `sku ${r.ozon_sku}` : '')}</div>
                        </div>
                      </td>
                      <td className="py-2.5 px-4 text-fg-muted truncate max-w-[240px]">{r.reason || '—'}</td>
                      <td className="py-2.5 px-4 text-right tabular-nums">{formatNumber(r.quantity)}</td>
                      <td className="py-2.5 px-4 text-right tabular-nums text-rose-700">
                        {r.amount != null ? formatCurrency(r.amount) : '—'}
                      </td>
                    </tr>
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
              <Button variant="ghost" onClick={() => setPage(Math.max(1, page - 1))} disabled={page <= 1} className="!h-8 !px-2">
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="tabular-nums">
                {page} / {totalPages}
                {isFetching && <Loader2 className="inline-block w-3 h-3 ml-2 animate-spin" />}
              </span>
              <Button variant="ghost" onClick={() => setPage(Math.min(totalPages, page + 1))} disabled={page >= totalPages} className="!h-8 !px-2">
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
