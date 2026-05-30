import { useMemo, useState } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  Receipt,
  Search,
  Download,
  ChevronLeft,
  ChevronRight,
  Loader2,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { TransactionsMonthly } from '@/components/TransactionsMonthly'
import { api, API_BASE_URL } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'

interface TxRow {
  time: string
  operation_type: string
  operation_type_name: string | null
  cabinet_id: string
  cabinet_name: string
  posting_number: string | null
  amount: number
  accruals_for_sale: number | null
  sale_commission: number | null
  description: string | null
  delivery_to_customer: number
  return_logistics: number
  last_mile: number
  storage: number
  placement: number
  acquiring: number
  advertising: number
  utilization: number
}

interface TxListResp {
  page: number
  page_size: number
  total: number
  sum_amount: number
  items: TxRow[]
}

interface OpTypeOption {
  operation_type: string
  operation_type_name: string | null
  count: number
}

const PAGE_SIZE = 50

const SERVICE_COLS: Array<[keyof TxRow, string]> = [
  ['delivery_to_customer', 'Доставка к клиенту'],
  ['return_logistics', 'Возвратная лог.'],
  ['last_mile', 'Last mile'],
  ['storage', 'Хранение'],
  ['placement', 'Размещение'],
  ['acquiring', 'Эквайринг'],
  ['advertising', 'Реклама'],
  ['utilization', 'Утилизация'],
]

type ViewMode = 'monthly' | 'all'

export function FinanceTransactions() {
  const [urlParams] = useSearchParams()
  // ?view=all из drill-down дня → сразу попадаем в плоский список
  const initialView: ViewMode = (urlParams.get('view') === 'all'
    || urlParams.get('date_from')
    || urlParams.get('date_to')) ? 'all' : 'monthly'
  const [viewMode, setViewMode] = useState<ViewMode>(initialView)
  const { selectedCabinetIds } = useCabinetStore()
  const [page, setPage] = useState(1)
  const [operationType, setOperationType] = useState('')
  const [search, setSearch] = useState('')
  const [dateFrom, setDateFrom] = useState(urlParams.get('date_from') || '')
  const [dateTo, setDateTo] = useState(urlParams.get('date_to') || '')
  const [expandedKey, setExpandedKey] = useState<string | null>(null)

  // Dropdown с типами операций
  const { data: types } = useQuery<OpTypeOption[]>({
    queryKey: ['finance', 'tx-types', selectedCabinetIds],
    queryFn: async () => {
      const params = new URLSearchParams()
      selectedCabinetIds.forEach((id) => params.append('cabinet_ids', id))
      const res = await api.get(`/finance/transactions/types?${params.toString()}`)
      return res.data
    },
  })

  const { data, isLoading, isFetching } = useQuery<TxListResp>({
    queryKey: ['finance', 'tx', page, operationType, search, dateFrom, dateTo, selectedCabinetIds],
    queryFn: async () => {
      const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) })
      selectedCabinetIds.forEach((id) => params.append('cabinet_ids', id))
      if (operationType) params.append('operation_type', operationType)
      if (search) params.append('search', search)
      if (dateFrom) params.append('date_from', dateFrom)
      if (dateTo) params.append('date_to', dateTo)
      const res = await api.get(`/finance/transactions/?${params.toString()}`)
      return res.data
    },
    placeholderData: keepPreviousData,
  })

  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const startIdx = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const endIdx = Math.min(total, page * PAGE_SIZE)

  const exportUrl = useMemo(() => {
    const params = new URLSearchParams()
    selectedCabinetIds.forEach((id) => params.append('cabinet_ids', id))
    if (operationType) params.append('operation_type', operationType)
    if (search) params.append('search', search)
    if (dateFrom) params.append('date_from', dateFrom)
    if (dateTo) params.append('date_to', dateTo)
    return `${API_BASE_URL}/finance/transactions/export.csv?${params.toString()}`
  }, [selectedCabinetIds, operationType, search, dateFrom, dateTo])

  const handleExport = async () => {
    // Скачиваем с auth-заголовком: fetch → blob → save-as
    const res = await fetch(exportUrl, {
      headers: { Authorization: `Bearer ${localStorage.getItem('flowoi_token') || ''}` },
    })
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `flowoi_transactions_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const resetFilters = () => {
    setOperationType('')
    setSearch('')
    setDateFrom('')
    setDateTo('')
    setPage(1)
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Транзакции Ozon</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            {viewMode === 'monthly'
              ? 'Помесячная сводка → клик на месяц → день → операции'
              : `${formatNumber(total)} операций · сумма по фильтру: ${formatCurrency(data?.sum_amount ?? 0)}`}
          </p>
        </div>
        <div className="inline-flex rounded-md border border-border-subtle p-0.5 text-xs">
          {([
            ['monthly', 'Помесячно'],
            ['all', 'Все операции'],
          ] as const).map(([k, l]) => (
            <button key={k} onClick={() => setViewMode(k)} className={cn(
              'px-3 py-1 rounded',
              viewMode === k ? 'bg-fg text-bg' : 'text-fg-muted hover:bg-bg-subtle',
            )}>{l}</button>
          ))}
        </div>
      </div>

      {viewMode === 'monthly' && <TransactionsMonthly />}

      {viewMode === 'all' && (
      <>
      <Card className="p-4 flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[220px]">
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
              placeholder="posting / тип / описание"
              className="pl-9"
            />
          </div>
        </div>
        <div>
          <label className="block text-[11px] font-medium text-fg-muted uppercase tracking-wider mb-1">
            Тип операции
          </label>
          <select
            value={operationType}
            onChange={(e) => {
              setOperationType(e.target.value)
              setPage(1)
            }}
            className="h-9 px-3 rounded-md border border-border bg-surface text-sm min-w-[200px] max-w-[280px]"
          >
            <option value="">все типы</option>
            {(types || []).map((t) => (
              <option key={t.operation_type} value={t.operation_type}>
                {t.operation_type_name || t.operation_type} ({formatNumber(t.count)})
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
        {(operationType || search || dateFrom || dateTo) && (
          <Button variant="ghost" onClick={resetFilters}>
            Сбросить
          </Button>
        )}
        <Button onClick={handleExport} variant="secondary">
          <Download className="w-4 h-4" /> CSV
        </Button>
      </Card>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 flex justify-center items-center text-fg-muted">
            <Loader2 className="w-5 h-5 animate-spin mr-2" /> Загрузка…
          </div>
        ) : total === 0 ? (
          <div className="py-20 flex flex-col items-center text-fg-muted">
            <Receipt className="w-8 h-8 mb-3 text-fg-subtle" />
            <p className="text-sm">Транзакции не найдены</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                  <th className="py-2.5 px-4 font-medium">дата</th>
                  <th className="py-2.5 px-4 font-medium">тип</th>
                  <th className="py-2.5 px-4 font-medium">кабинет</th>
                  <th className="py-2.5 px-4 font-medium">posting</th>
                  <th className="py-2.5 px-4 font-medium text-right">сумма</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {(data?.items || []).map((t, idx) => {
                  const key = `${t.time}-${idx}`
                  const expanded = expandedKey === key
                  const dt = new Date(t.time).toLocaleDateString('ru-RU', {
                    day: '2-digit',
                    month: '2-digit',
                    year: '2-digit',
                  })
                  const isExpense = t.amount < 0
                  return (
                    <>
                      <tr
                        key={key}
                        onClick={() => setExpandedKey(expanded ? null : key)}
                        className={cn(
                          'cursor-pointer hover:bg-bg-subtle/50',
                          expanded && 'bg-bg-subtle/60',
                        )}
                      >
                        <td className="py-2.5 px-4 text-fg-muted tabular-nums whitespace-nowrap">
                          {dt}
                        </td>
                        <td className="py-2.5 px-4 text-fg truncate max-w-[280px]">
                          {t.operation_type_name || t.operation_type}
                        </td>
                        <td className="py-2.5 px-4 text-fg">{t.cabinet_name}</td>
                        <td className="py-2.5 px-4 font-mono text-xs text-fg-muted">
                          {t.posting_number || '—'}
                        </td>
                        <td
                          className={cn(
                            'py-2.5 px-4 text-right tabular-nums font-mono',
                            isExpense ? 'text-rose-700' : 'text-emerald-700',
                          )}
                        >
                          {formatCurrency(t.amount)}
                        </td>
                      </tr>
                      {expanded && (
                        <tr className="bg-bg-subtle/40">
                          <td colSpan={5} className="px-4 py-3">
                            <div className="flex flex-col gap-2 text-xs">
                              {t.description && (
                                <div className="text-fg-muted">{t.description}</div>
                              )}
                              <div className="flex flex-wrap gap-x-6 gap-y-1.5 text-fg-muted">
                                {t.accruals_for_sale !== null && (
                                  <span>
                                    начислено: <span className="text-fg font-mono">{formatCurrency(t.accruals_for_sale)}</span>
                                  </span>
                                )}
                                {t.sale_commission !== null && (
                                  <span>
                                    комиссия: <span className="text-fg font-mono">{formatCurrency(t.sale_commission)}</span>
                                  </span>
                                )}
                              </div>
                              {/* Services breakdown */}
                              {SERVICE_COLS.some(([k]) => (t[k] as number) > 0) && (
                                <div className="pt-2 mt-1 border-t border-border-subtle grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-1">
                                  {SERVICE_COLS.map(([k, label]) => {
                                    const v = t[k] as number
                                    if (!v) return null
                                    return (
                                      <div key={String(k)} className="flex justify-between">
                                        <span className="text-fg-muted">{label}</span>
                                        <span className="font-mono text-fg">{formatCurrency(v)}</span>
                                      </div>
                                    )
                                  })}
                                </div>
                              )}
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
      </>
      )}
    </div>
  )
}
