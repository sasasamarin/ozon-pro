/**
 * /alerts/history — журнал всех срабатываний.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { History, CheckCircle2, AlertCircle, AlertTriangle, Info } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface Alert {
  id: string; marker_type: string; severity: string
  message: string; triggered_at: string; resolved_at: string | null
}

const TYPE_LABEL: Record<string, string> = {
  stockout: 'Кончается', overstock: 'Затоварен',
  sales_drop: 'Падение продаж', sales_spike: 'Скачок',
  margin_below_min: 'Маржа↓', price_below_cost: 'Цена<с/с',
  credit_payment_due: 'Платёж', negative_review: 'Отзыв 1-3⭐',
  return_received: 'Возврат',
}

export function AlertsHistory() {
  const [days, setDays] = useState(30)
  const [filter, setFilter] = useState('')

  const { data: rows = [] } = useQuery<Alert[]>({
    queryKey: ['alerts-history', days, filter],
    queryFn: async () => {
      const url = `/alerts/history?days=${days}${filter ? `&marker_type=${filter}` : ''}`
      return (await api.get(url)).data
    },
  })

  // Группировка по дням
  const byDay: Record<string, Alert[]> = {}
  for (const r of rows) {
    const d = r.triggered_at.slice(0, 10)
    ;(byDay[d] = byDay[d] || []).push(r)
  }

  const stats = {
    total: rows.length,
    resolved: rows.filter((r) => r.resolved_at).length,
    critical: rows.filter((r) => r.severity === 'critical').length,
  }

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
            <History className="w-6 h-6 text-blue-500" />
            История алертов
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            Все срабатывания за период. Закрытые помечены зелёным.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={filter} onChange={(e) => setFilter(e.target.value)}
                  className="px-2 py-1 border border-border-subtle rounded text-sm bg-bg">
            <option value="">Все типы</option>
            {Object.entries(TYPE_LABEL).map(([k, l]) => (
              <option key={k} value={k}>{l}</option>
            ))}
          </select>
          <select value={days} onChange={(e) => setDays(+e.target.value)}
                  className="px-2 py-1 border border-border-subtle rounded text-sm bg-bg">
            <option value={7}>7д</option>
            <option value={30}>30д</option>
            <option value={90}>90д</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Card className="p-3">
          <div className="text-xs text-fg-muted">Всего срабатываний</div>
          <div className="text-xl font-semibold tabular-nums">{stats.total}</div>
        </Card>
        <Card className="p-3">
          <div className="text-xs text-fg-muted">Закрыто</div>
          <div className="text-xl font-semibold tabular-nums text-emerald-700">{stats.resolved}</div>
        </Card>
        <Card className="p-3">
          <div className="text-xs text-fg-muted">Critical</div>
          <div className="text-xl font-semibold tabular-nums text-rose-700">{stats.critical}</div>
        </Card>
      </div>

      <div className="space-y-3">
        {Object.entries(byDay).sort(([a], [b]) => b.localeCompare(a)).map(([day, list]) => (
          <Card key={day} className="overflow-hidden">
            <div className="px-3 py-2 border-b border-border-subtle bg-bg-subtle/30">
              <div className="flex justify-between text-sm">
                <span className="font-semibold">{day}</span>
                <span className="text-fg-muted">{list.length} событий</span>
              </div>
            </div>
            <div className="divide-y divide-border-subtle/30">
              {list.map((a) => (
                <div key={a.id} className="px-3 py-2 flex items-start gap-3">
                  <div className="shrink-0 pt-0.5">
                    {a.severity === 'critical' && <AlertCircle className="w-4 h-4 text-rose-600" />}
                    {a.severity === 'warning' && <AlertTriangle className="w-4 h-4 text-amber-600" />}
                    {a.severity === 'info' && <Info className="w-4 h-4 text-blue-600" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-[10px] px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                        {TYPE_LABEL[a.marker_type] || a.marker_type}
                      </span>
                      {a.resolved_at && (
                        <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-100 text-emerald-700 inline-flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" /> закрыт
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-fg">{a.message}</div>
                  </div>
                  <div className="text-[11px] text-fg-muted shrink-0 tabular-nums">
                    {new Date(a.triggered_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        ))}
        {rows.length === 0 && (
          <Card className="p-8 text-center text-fg-muted">
            Нет срабатываний за выбранный период.
          </Card>
        )}
      </div>
    </div>
  )
}
