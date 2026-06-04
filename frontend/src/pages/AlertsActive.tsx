/**
 * /alerts — активные алерты.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Bell, CheckCircle2, RefreshCw, AlertTriangle, AlertCircle, Info } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { AskAIButton } from '@/components/AskAIButton'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface Alert {
  id: string; marker_type: string; severity: string
  message: string; ozon_account_id: string | null
  triggered_at: string; resolved_at: string | null
}

const TYPE_LABEL: Record<string, string> = {
  stockout: 'Кончается товар', overstock: 'Затоварен',
  sales_drop: 'Падение продаж', sales_spike: 'Скачок продаж',
  low_conversion: 'Низкая конверсия', competitor_dump: 'Демпинг конкурента',
  price_below_cost: 'Цена ниже с/с', margin_below_min: 'Маржа критическая',
  cashflow_gap: 'Кассовый разрыв', ad_budget_exceeded: 'Превышен бюджет рекламы',
  credit_payment_due: 'Платёж по кредиту', tax_due: 'Срок налога',
  negative_review: 'Негативный отзыв', rating_drop: 'Падение рейтинга',
  position_drop: 'Падение позиции', fbs_not_shipped: 'FBS не отгружен',
  return_received: 'Возврат принят', commission_change: 'Изменение комиссии',
}

const SEV_TONE: Record<string, string> = {
  critical: 'bg-rose-50 border-rose-300 text-rose-700',
  warning: 'bg-amber-50 border-amber-300 text-amber-700',
  info: 'bg-blue-50 border-blue-200 text-blue-700',
}

function SeverityIcon({ severity, className }: { severity: string; className?: string }) {
  if (severity === 'critical') return <AlertCircle className={cn('text-rose-600', className)} />
  if (severity === 'warning') return <AlertTriangle className={cn('text-amber-600', className)} />
  return <Info className={cn('text-blue-600', className)} />
}

export function AlertsActive() {
  const qc = useQueryClient()
  const [severityFilter, setSeverityFilter] = useState('')

  const { data: alerts = [], isFetching } = useQuery<Alert[]>({
    queryKey: ['alerts-active', severityFilter],
    queryFn: async () => {
      const url = severityFilter ? `/alerts/active?severity=${severityFilter}` : '/alerts/active'
      return (await api.get(url)).data
    },
  })

  const runChecks = useMutation({
    mutationFn: async () => (await api.post('/alerts/run-checks')).data,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['alerts-active'] })
      alert(`Запущено. Новых алертов: ${data.total}`)
    },
    onError: () => alert('Ошибка при запуске проверки'),
  })

  const resolve = useMutation({
    mutationFn: async (id: string) => (await api.post(`/alerts/${id}/resolve`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts-active'] }),
  })

  // Группировка по типу
  const byType: Record<string, Alert[]> = {}
  for (const a of alerts) {
    (byType[a.marker_type] = byType[a.marker_type] || []).push(a)
  }

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
            <Bell className="w-6 h-6 text-amber-500" />
            Активные алерты
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            События, требующие внимания. Закрывайте по мере отработки.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}
                  className="px-2 py-1 border border-border-subtle rounded text-sm bg-bg">
            <option value="">Все приоритеты</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="info">Info</option>
          </select>
          <Button variant="secondary" onClick={() => runChecks.mutate()}
                  disabled={runChecks.isPending}
                  className="inline-flex items-center gap-1">
            <RefreshCw className={cn('w-4 h-4', runChecks.isPending && 'animate-spin')} />
            {runChecks.isPending ? 'Проверяю…' : 'Запустить проверки'}
          </Button>
          <AskAIButton
            context={{ type: 'screen', source_page: 'alerts-active',
              source_label: 'Активные алерты', metrics: ['severity', 'marker_type'] }}
            question="Что среди этих алертов важнее всего сделать сегодня?"
          />
        </div>
      </div>

      {alerts.length === 0 && !isFetching && (
        <Card className="p-8 text-center">
          <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto mb-3" />
          <div className="text-fg font-medium">Активных алертов нет</div>
          <div className="text-sm text-fg-muted mt-1">
            Запустите проверки, чтобы убедиться, или сходите в /alerts/settings настроить пороги.
          </div>
        </Card>
      )}

      {Object.entries(byType).map(([type, list]) => (
        <Card key={type} className="overflow-hidden">
          <div className="p-3 border-b border-border-subtle bg-bg-subtle/30">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-fg">{TYPE_LABEL[type] || type}</h3>
              <span className="text-xs text-fg-muted">{list.length} событий</span>
            </div>
          </div>
          <div className="divide-y divide-border-subtle/40">
            {list.map((a) => (
              <div key={a.id} className={cn(
                'p-3 flex items-start gap-3 border-l-4',
                SEV_TONE[a.severity] || 'border-l-slate-300',
              )}>
                <SeverityIcon severity={a.severity} className="w-5 h-5 mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-fg">{a.message}</div>
                  <div className="text-[11px] text-fg-muted mt-1">
                    {new Date(a.triggered_at).toLocaleString('ru-RU')}
                  </div>
                </div>
                <Button variant="ghost" onClick={() => resolve.mutate(a.id)}
                        className="text-xs px-2 py-1 shrink-0">
                  <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Закрыть
                </Button>
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  )
}
