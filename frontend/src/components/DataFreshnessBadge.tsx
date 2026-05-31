/**
 * Бейдж «Данные актуальны» в Topbar — показывает свежесть всех sync-источников.
 * Клик → раскрывается список с временем последнего обновления каждой группы.
 */
import { useState, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, AlertTriangle, AlertCircle, ChevronDown } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface SourceFreshness {
  source: string
  label: string
  last_at: string | null
  minutes_ago: number | null
  status: 'fresh' | 'stale' | 'no_data'
}
interface HealthResp {
  overall_status: 'ok' | 'warn' | 'critical'
  fresh_count: number
  stale_count: number
  total_count: number
  sources: SourceFreshness[]
}

function formatAgo(min: number | null): string {
  if (min == null) return '—'
  if (min < 60) return `${min} мин назад`
  const h = Math.floor(min / 60)
  if (h < 24) return `${h} ч назад`
  const d = Math.floor(h / 24)
  return `${d} дн назад`
}

export function DataFreshnessBadge() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const { data } = useQuery<HealthResp>({
    queryKey: ['system', 'health'],
    queryFn: async () => (await api.get('/system/health')).data,
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  })

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  if (!data) return null

  const Icon = data.overall_status === 'ok' ? CheckCircle2
             : data.overall_status === 'warn' ? AlertTriangle
             : AlertCircle
  const tone =
    data.overall_status === 'ok'   ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
  : data.overall_status === 'warn' ? 'text-amber-700 bg-amber-50 border-amber-200'
  :                                  'text-rose-700 bg-rose-50 border-rose-200'

  const label =
    data.overall_status === 'ok' ? 'Данные актуальны'
    : `Устарели: ${data.stale_count}/${data.total_count}`

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-xs',
          tone,
        )}
      >
        <Icon className="w-3.5 h-3.5" />
        <span className="font-medium">{label}</span>
        <ChevronDown className="w-3 h-3 opacity-60" />
      </button>
      {open && (
        <div className="absolute right-0 top-9 z-40 w-72 bg-bg border border-border rounded-lg shadow-elev p-2">
          <div className="text-[10px] text-fg-muted uppercase tracking-wider px-2 py-1 mb-1">
            Свежесть источников
          </div>
          <ul className="space-y-0.5">
            {data.sources.map((s) => (
              <li key={s.source} className="flex items-center gap-2 px-2 py-1.5 text-xs">
                <span className={cn(
                  'w-1.5 h-1.5 rounded-full shrink-0',
                  s.status === 'fresh' ? 'bg-emerald-500'
                  : s.status === 'stale' ? 'bg-amber-500'
                  : 'bg-slate-400',
                )} />
                <span className="flex-1 text-fg">{s.label}</span>
                <span className="text-fg-muted tabular-nums">
                  {s.status === 'no_data' ? 'нет данных' : formatAgo(s.minutes_ago)}
                </span>
              </li>
            ))}
          </ul>
          <p className="text-[10px] text-fg-subtle mt-1 px-2">
            Sync крутится по cron: товары/реклама/заказы каждый час, остатки 2×/час,
            транзакции и аналитика ночью.
          </p>
        </div>
      )}
    </div>
  )
}
