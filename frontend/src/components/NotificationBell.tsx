/**
 * Bell иконка с popover активных алертов.
 *
 * Источник: /api/v1/alerts/unread-summary — refetch каждые 60 сек.
 */
import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Bell, AlertCircle, AlertTriangle, Info, CheckCircle2 } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface AlertRow {
  id: string; marker_type: string; severity: string
  message: string; triggered_at: string; resolved_at: string | null
}
interface UnreadSummary {
  count: number
  critical_count: number
  warning_count: number
  recent: AlertRow[]
}

const TYPE_LABEL: Record<string, string> = {
  stockout: 'Кончается', overstock: 'Затоварен',
  sales_drop: 'Падение продаж', margin_below_min: 'Маржа↓',
  price_below_cost: 'Цена<с/с', credit_payment_due: 'Платёж',
  cashflow_gap: 'Кассовый разрыв', negative_review: '1-3⭐',
  return_received: 'Возврат',
}

export function NotificationBell() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const { data } = useQuery<UnreadSummary>({
    queryKey: ['alerts-unread'],
    queryFn: async () => (await api.get('/alerts/unread-summary')).data,
    refetchInterval: 60_000, // обновление раз в минуту
  })

  const resolve = useMutation({
    mutationFn: async (id: string) => (await api.post(`/alerts/${id}/resolve`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts-unread'] }),
  })

  useEffect(() => {
    function close(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const count = data?.count || 0
  const hasCritical = (data?.critical_count || 0) > 0

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="relative h-9 w-9 inline-flex items-center justify-center rounded-md hover:bg-bg-subtle transition-colors"
        title="Алерты"
      >
        <Bell className={cn('w-4.5 h-4.5',
          hasCritical ? 'text-rose-600' : count > 0 ? 'text-amber-600' : 'text-fg-muted')} />
        {count > 0 && (
          <span className={cn(
            'absolute -top-0.5 -right-0.5 text-[9px] font-semibold rounded-full px-1.5 min-w-[16px] h-4 inline-flex items-center justify-center',
            hasCritical ? 'bg-rose-600 text-white' : 'bg-amber-500 text-white',
          )}>{count > 99 ? '99+' : count}</span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-11 z-40 w-[360px] bg-surface border border-border rounded-lg shadow-elev overflow-hidden animate-fade-in">
          <div className="px-3 py-2 border-b border-border-subtle flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-fg">Активные алерты</div>
              {data && data.count > 0 && (
                <div className="text-[11px] text-fg-muted mt-0.5">
                  {data.critical_count > 0 && <span className="text-rose-700 mr-2">⚠ {data.critical_count} critical</span>}
                  {data.warning_count > 0 && <span className="text-amber-700">{data.warning_count} warning</span>}
                </div>
              )}
            </div>
            <button onClick={() => { setOpen(false); navigate('/alerts') }}
                    className="text-xs text-blue-600 hover:underline">
              Все →
            </button>
          </div>

          {data && data.count === 0 ? (
            <div className="p-6 text-center">
              <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto mb-2" />
              <div className="text-sm text-fg">Всё под контролем</div>
              <div className="text-[11px] text-fg-muted mt-1">Активных алертов нет</div>
            </div>
          ) : (
            <div className="max-h-[420px] overflow-y-auto divide-y divide-border-subtle/40">
              {(data?.recent || []).map((a) => (
                <div key={a.id} className="px-3 py-2 hover:bg-bg-subtle/30 flex items-start gap-2.5">
                  <div className="shrink-0 pt-0.5">
                    {a.severity === 'critical' && <AlertCircle className="w-4 h-4 text-rose-600" />}
                    {a.severity === 'warning' && <AlertTriangle className="w-4 h-4 text-amber-600" />}
                    {a.severity === 'info' && <Info className="w-4 h-4 text-blue-600" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 uppercase font-medium">
                        {TYPE_LABEL[a.marker_type] || a.marker_type}
                      </span>
                      <span className="text-[10px] text-fg-muted">
                        {new Date(a.triggered_at).toLocaleString('ru-RU', {
                          day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
                        })}
                      </span>
                    </div>
                    <div className="text-xs text-fg leading-snug">{a.message}</div>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); resolve.mutate(a.id) }}
                    title="Отметить как закрытый"
                    className="shrink-0 p-1 hover:bg-emerald-100 rounded">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                  </button>
                </div>
              ))}
              {data && data.count > 5 && (
                <div className="px-3 py-2 text-center text-[11px] text-fg-muted">
                  Ещё {data.count - 5} активных — открой /alerts
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
