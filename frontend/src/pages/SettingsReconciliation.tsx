/**
 * Страница «Сверка с отчётом Ozon» в настройках.
 * - Список сверок по кабинетам и месяцам с расхождением
 * - Детальная разбивка по SKU за месяц
 * - Кнопка ручного запуска (на случай если ждать понедельника не хочется)
 * - Объяснение «зачем» — для доверия (принцип юзера: «каждая цифра объяснена»)
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, AlertTriangle, RefreshCw, Loader2, ChevronRight, ChevronDown } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'

interface ReconcileRow {
  ozon_account_id: string
  cabinet_name: string
  year: number
  month: number
  total_revenue: number | null
  total_payout_real: number | null
  total_payout_model: number | null
  diff_pct: number | null
  alert: boolean
  created_at: string
}

interface SkuDiff {
  cabinet: string
  sku: number
  name: string
  offer_id: string | null
  qty: number
  revenue: number
  payout_real: number
  payout_model: number
  diff_rub: number
  diff_pct: number | null
  comm_pct_used: number
}

const MONTH_RU = ['', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']

export function SettingsReconciliation() {
  const [expanded, setExpanded] = useState<string | null>(null)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery<ReconcileRow[]>({
    queryKey: ['reconciliation', 'realization'],
    queryFn: async () => (await api.get('/reconciliation/realization')).data,
  })

  const runManual = useMutation({
    mutationFn: async () => (await api.post('/reconciliation/realization/run')).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reconciliation'] })
      alert('Сверка запущена в фоне. Результат появится через 1-2 минуты.')
    },
  })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Сверка с отчётом Ozon</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Авто-сверка нашей модели прибыли с официальной реализацией Ozon. Каждый понедельник в 06:00.
          </p>
        </div>
        <button
          onClick={() => runManual.mutate()}
          disabled={runManual.isPending}
          className="inline-flex items-center gap-2 px-3 py-2 text-sm border border-border-subtle rounded-md hover:bg-bg-subtle disabled:opacity-50"
        >
          {runManual.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          Запустить сейчас (за прошлый месяц)
        </button>
      </div>

      {/* Объяснение */}
      <Card className="p-4 bg-blue-50/60 border-blue-200/60">
        <h3 className="text-sm font-semibold text-blue-900 mb-1.5">Как это работает</h3>
        <ul className="text-sm text-blue-900/90 leading-relaxed space-y-1 list-disc list-inside">
          <li><strong>Отчёт Ozon</strong> — официальная реализация из <code>/v2/finance/realization</code>. Формируется Ozon с лагом ~15 дней после конца месяца, копейка-в-копейку.</li>
          <li><strong>Наша модель</strong> — payout = <code>seller_price × (1 − комиссия) − логистика</code>. Считается из транзакций в реальном времени.</li>
          <li>Сравниваем итог «к перечислению» обеих моделей per-товар. Если расхождение &gt; 5% — алерт.</li>
          <li>До 5% — норма (округления, граничные дни между периодами).</li>
        </ul>
      </Card>

      {/* Таблица */}
      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 flex justify-center text-fg-muted">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : !data || data.length === 0 ? (
          <div className="py-12 text-center text-fg-muted">
            <p className="text-sm">Сверка ещё не запускалась.</p>
            <p className="text-xs mt-1">Запусти вручную или подожди понедельника 06:00.</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-bg-subtle/50 border-b border-border-subtle">
              <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                <th className="py-2.5 px-4 w-6"></th>
                <th className="py-2.5 px-4">кабинет</th>
                <th className="py-2.5 px-4">период</th>
                <th className="py-2.5 px-4 text-right">выручка</th>
                <th className="py-2.5 px-4 text-right">payout (Ozon)</th>
                <th className="py-2.5 px-4 text-right">payout (модель)</th>
                <th className="py-2.5 px-4 text-right">δ</th>
                <th className="py-2.5 px-4">статус</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {data.map((r) => {
                const key = `${r.ozon_account_id}-${r.year}-${r.month}`
                const isExpanded = expanded === key
                return (
                  <ReconcileRowComponent
                    key={key}
                    row={r}
                    expanded={isExpanded}
                    onToggle={() => setExpanded(isExpanded ? null : key)}
                  />
                )
              })}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}

function ReconcileRowComponent({
  row, expanded, onToggle,
}: {
  row: ReconcileRow
  expanded: boolean
  onToggle: () => void
}) {
  const { data: detail } = useQuery<SkuDiff[]>({
    queryKey: ['reconciliation', 'realization', row.year, row.month],
    enabled: expanded,
    queryFn: async () =>
      (await api.get(`/reconciliation/realization/${row.year}/${row.month}`)).data,
  })

  return (
    <>
      <tr className="hover:bg-bg-subtle/40 cursor-pointer" onClick={onToggle}>
        <td className="py-2.5 px-4 text-fg-muted">
          {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </td>
        <td className="py-2.5 px-4 font-medium">{row.cabinet_name}</td>
        <td className="py-2.5 px-4 text-fg-muted">{MONTH_RU[row.month]} {row.year}</td>
        <td className="py-2.5 px-4 text-right tabular-nums">
          {row.total_revenue != null ? formatCurrency(row.total_revenue) : '—'}
        </td>
        <td className="py-2.5 px-4 text-right tabular-nums">
          {row.total_payout_real != null ? formatCurrency(row.total_payout_real) : '—'}
        </td>
        <td className="py-2.5 px-4 text-right tabular-nums text-fg-muted">
          {row.total_payout_model != null ? formatCurrency(row.total_payout_model) : '—'}
        </td>
        <td className={cn('py-2.5 px-4 text-right tabular-nums font-semibold',
          row.alert ? 'text-rose-700' :
          row.diff_pct != null && Math.abs(row.diff_pct) > 2 ? 'text-amber-700' :
          'text-emerald-700')}>
          {row.diff_pct != null ? `${row.diff_pct > 0 ? '+' : ''}${row.diff_pct.toFixed(2)}%` : '—'}
        </td>
        <td className="py-2.5 px-4">
          {row.alert ? (
            <span className="inline-flex items-center gap-1 text-xs text-rose-700">
              <AlertTriangle className="w-3.5 h-3.5" /> расхождение
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-xs text-emerald-700">
              <CheckCircle2 className="w-3.5 h-3.5" /> ок
            </span>
          )}
        </td>
      </tr>
      {expanded && detail && (
        <tr>
          <td colSpan={8} className="bg-bg-subtle/40 px-6 py-4">
            <div className="text-xs font-medium text-fg-muted uppercase tracking-wider mb-2">
              Разбивка по SKU
            </div>
            <table className="w-full text-xs">
              <thead className="text-fg-subtle uppercase">
                <tr className="text-left">
                  <th className="py-1.5 px-2 font-medium">SKU</th>
                  <th className="py-1.5 px-2 font-medium">offer</th>
                  <th className="py-1.5 px-2 font-medium text-right">qty</th>
                  <th className="py-1.5 px-2 font-medium text-right">payout Ozon</th>
                  <th className="py-1.5 px-2 font-medium text-right">payout модель</th>
                  <th className="py-1.5 px-2 font-medium text-right">δ ₽</th>
                  <th className="py-1.5 px-2 font-medium text-right">δ %</th>
                </tr>
              </thead>
              <tbody>
                {detail.slice(0, 50).map((s, i) => (
                  <tr key={i} className="border-t border-border-subtle/30">
                    <td className="py-1.5 px-2 font-mono">{s.sku}</td>
                    <td className="py-1.5 px-2 text-fg-muted truncate max-w-[200px]">{s.offer_id || s.name}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{formatNumber(s.qty)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{formatCurrency(s.payout_real)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums text-fg-muted">{formatCurrency(s.payout_model)}</td>
                    <td className={cn('py-1.5 px-2 text-right tabular-nums', s.diff_rub >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
                      {s.diff_rub > 0 ? '+' : ''}{formatCurrency(s.diff_rub)}
                    </td>
                    <td className={cn('py-1.5 px-2 text-right tabular-nums font-semibold',
                      s.diff_pct != null && Math.abs(s.diff_pct) > 5 ? 'text-rose-700' :
                      s.diff_pct != null && Math.abs(s.diff_pct) > 2 ? 'text-amber-700' :
                      'text-emerald-700')}>
                      {s.diff_pct != null ? `${s.diff_pct > 0 ? '+' : ''}${s.diff_pct.toFixed(1)}%` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {detail.length > 50 && (
              <p className="text-xs text-fg-subtle mt-2">… ещё {detail.length - 50} SKU</p>
            )}
          </td>
        </tr>
      )}
    </>
  )
}
