/**
 * Бейдж сверки модели с отчётом Ozon (для Topbar или Settings).
 * - 🟢 OK = модель совпадает с realization (расхождение < 5%)
 * - 🔴 WARN = расхождение > 5% — алерт юзеру
 * - ⚪ no_data = сверка ещё не запускалась
 */
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { CheckCircle2, AlertTriangle, HelpCircle } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface ReconcileStatus {
  status: 'ok' | 'warn' | 'no_data'
  title: string
  description: string
  last_reconciled_at: string | null
  worst_diff_pct: number | null
  rows_count: number
  data_period_year?: number | null
  data_period_month?: number | null
  data_period_label?: string | null
}

export function ReconcileBadge({ compact = false }: { compact?: boolean }) {
  const { data } = useQuery<ReconcileStatus>({
    queryKey: ['reconciliation', 'status'],
    queryFn: async () => (await api.get('/reconciliation/status')).data,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  })
  if (!data) return null

  const Icon = data.status === 'ok' ? CheckCircle2 : data.status === 'warn' ? AlertTriangle : HelpCircle
  const tone =
    data.status === 'ok' ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
    : data.status === 'warn' ? 'text-rose-700 bg-rose-50 border-rose-200'
    : 'text-slate-600 bg-slate-50 border-slate-200'

  // Подпись справа — ПЕРИОД сверенных данных, не дата прогона.
  // «Сверено с Ozon · Апрель 2026» — юзер сразу понимает за какой месяц.
  const subtitle = data.data_period_label || null

  return (
    <Link to="/settings/reconciliation"
          className={cn(
            'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-xs',
            tone,
          )}
          title={data.description}>
      <Icon className="w-3.5 h-3.5" />
      {compact ? (
        <span className="font-medium">{data.title}</span>
      ) : (
        <>
          <span className="font-medium">{data.title}</span>
          {subtitle && data.status !== 'ok' && (
            <span className="opacity-60 text-[10px]">· данные по {subtitle}</span>
          )}
        </>
      )}
    </Link>
  )
}
