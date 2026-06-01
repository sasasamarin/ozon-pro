/**
 * Матрица покрытия XLSX «Экономика магазина» — кабинет × месяцы (последние 12).
 *
 * Принцип «честность»: юзер видит не только ЧТО загружено, но и ЧЕГО НЕ ХВАТАЕТ.
 * Без этого пустые месяцы выглядят как «всё нормально», хотя там storage = 0.
 *
 * Каждая ячейка:
 *  ✓ зелёная — XLSX загружен (тултип: «загр. ДД.ММ, X SKU»)
 *  ✗ серая   — пусто (storage будет 0, остальное оценка)
 *  ⏳ синяя  — текущий месяц (Ozon формирует отчёт до 5-10 числа след. месяца)
 *
 * Используется на странице импорта (полная) и в баннере P&L (компактная).
 */
import { useQuery } from '@tanstack/react-query'
import { Loader2, Check, X as XIcon, Clock } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface CoverageResp {
  cabinets: { id: string; name: string }[]
  months: string[]
  coverage: Record<string, Record<string, { sku_count: number; imported_at: string }>>
}

const MONTH_NAMES_RU = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

function monthShort(iso: string): string {
  const d = new Date(iso)
  return `${MONTH_NAMES_RU[d.getMonth()]} ${String(d.getFullYear()).slice(2)}`
}

function isCurrentMonth(iso: string): boolean {
  const d = new Date(iso)
  const now = new Date()
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth()
}

export function XlsxCoverageMatrix({ monthsBack = 12, compact = false }: { monthsBack?: number; compact?: boolean }) {
  const { data, isLoading } = useQuery<CoverageResp>({
    queryKey: ['unit-economy-coverage', monthsBack],
    queryFn: async () => (await api.get(`/finance/unit-economy/coverage?months_back=${monthsBack}`)).data,
    staleTime: 60_000,
  })

  if (isLoading) {
    return <div className="flex items-center gap-2 text-xs text-fg-muted py-3"><Loader2 className="w-4 h-4 animate-spin" /> Загружаю покрытие…</div>
  }
  if (!data || data.cabinets.length === 0) {
    return <p className="text-xs text-fg-muted">Нет кабинетов.</p>
  }

  // Считаем pure статистику для шапки
  const totalCells = data.cabinets.length * data.months.length
  const loadedCells = data.cabinets.reduce(
    (s, c) => s + Object.keys(data.coverage[c.id] || {}).length, 0,
  )
  const coveragePct = totalCells > 0 ? Math.round(loadedCells / totalCells * 100) : 0

  return (
    <div className={cn(compact ? '' : 'space-y-3')}>
      {!compact && (
        <div className="flex items-center justify-between flex-wrap gap-2 text-sm">
          <div className="text-fg-muted">
            <strong className="text-fg">Покрытие XLSX:</strong>{' '}
            {loadedCells} из {totalCells} ячеек ({coveragePct}%) за последние {monthsBack} мес.
          </div>
          <div className="flex items-center gap-3 text-[11px] text-fg-muted">
            <span className="inline-flex items-center gap-1">
              <span className="inline-flex w-4 h-4 items-center justify-center rounded bg-emerald-100 text-emerald-700">
                <Check className="w-3 h-3" />
              </span>
              загружен
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="inline-flex w-4 h-4 items-center justify-center rounded bg-blue-100 text-blue-700">
                <Clock className="w-3 h-3" />
              </span>
              текущий
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="inline-flex w-4 h-4 items-center justify-center rounded bg-bg-subtle text-fg-subtle">
                <XIcon className="w-3 h-3" />
              </span>
              нет данных
            </span>
          </div>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="text-xs border-collapse">
          <thead>
            <tr>
              <th className="text-left text-fg-muted font-medium pr-3 py-1.5 sticky left-0 bg-bg">Кабинет</th>
              {data.months.map((m) => (
                <th key={m} className={cn(
                  'px-1.5 py-1.5 font-medium text-center min-w-[42px]',
                  isCurrentMonth(m) ? 'text-blue-700' : 'text-fg-muted',
                )}>
                  {monthShort(m)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.cabinets.map((c) => {
              const cabCoverage = data.coverage[c.id] || {}
              return (
                <tr key={c.id}>
                  <td className="pr-3 py-1 font-medium text-fg sticky left-0 bg-bg">{c.name}</td>
                  {data.months.map((m) => {
                    const cell = cabCoverage[m]
                    const isCur = isCurrentMonth(m)
                    let bg: string, ic: React.ReactNode, title: string
                    if (cell) {
                      bg = 'bg-emerald-100 text-emerald-700'
                      ic = <Check className="w-3.5 h-3.5" />
                      const importedDate = new Date(cell.imported_at).toLocaleDateString('ru', { day: '2-digit', month: '2-digit' })
                      title = `${monthShort(m)}: загружен ${importedDate}, ${cell.sku_count} SKU`
                    } else if (isCur) {
                      bg = 'bg-blue-50 text-blue-600 border border-dashed border-blue-300'
                      ic = <Clock className="w-3.5 h-3.5" />
                      title = `${monthShort(m)}: текущий месяц, Ozon сформирует отчёт после 5-10 числа след. месяца`
                    } else {
                      bg = 'bg-bg-subtle text-fg-subtle'
                      ic = <XIcon className="w-3.5 h-3.5" />
                      title = `${monthShort(m)}: XLSX не загружен — storage=0, остальное оценка`
                    }
                    return (
                      <td key={m} className="px-1 py-1 text-center" title={title}>
                        <span className={cn('inline-flex w-6 h-6 items-center justify-center rounded', bg)}>
                          {ic}
                        </span>
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
