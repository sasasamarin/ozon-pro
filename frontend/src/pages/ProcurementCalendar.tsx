/**
 * /procurement/calendar — таймлайн поставок.
 *
 * Источник: SupplierOrder, группировка по expected_date (неделя/месяц).
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarDays, AlertTriangle, Truck, CheckCircle2, Package } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { AskAIButton } from '@/components/AskAIButton'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'

interface CalOrder {
  id: string; supplier_id: string | null; supplier_name: string | null
  product_id: string; product_name: string; offer_id: string
  qty: number; total_rub: number
  order_date: string; expected_date: string | null; received_date: string | null
  status: string; overdue_days: number
}
interface CalBucket {
  period: string; label: string; orders_count: number; total_value_rub: number
  by_status: Record<string, number>; items: CalOrder[]
}
interface Resp {
  granularity: string
  buckets: CalBucket[]
  summary: {
    total_orders: number; total_value_rub: number
    overdue_count: number; upcoming_30d_value_rub: number
    period_from: string; period_to: string
  }
}

const STATUS_LABEL: Record<string, string> = {
  created: 'создан', paid: 'оплачен', in_transit: 'в пути',
  received: 'получен', partial: 'частично',
}
const STATUS_TONE: Record<string, string> = {
  created: 'bg-slate-100 text-slate-700',
  paid: 'bg-blue-100 text-blue-700',
  in_transit: 'bg-amber-100 text-amber-700',
  received: 'bg-emerald-100 text-emerald-700',
  partial: 'bg-purple-100 text-purple-700',
}

export function ProcurementCalendar() {
  const [granularity, setGranularity] = useState<'week' | 'month'>('week')
  const [daysAhead, setDaysAhead] = useState(90)

  const { data } = useQuery<Resp>({
    queryKey: ['procurement-calendar', granularity, daysAhead],
    queryFn: async () =>
      (await api.get(`/procurement/calendar/calendar?granularity=${granularity}&days_ahead=${daysAhead}`)).data,
  })

  const s = data?.summary
  const buckets = data?.buckets || []

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
            <CalendarDays className="w-6 h-6 text-blue-500" />
            Календарь поставок
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            Когда приходят заказы поставщикам. Просрочки — относительно сегодня.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={granularity} onChange={(e) => setGranularity(e.target.value as any)}
                  className="px-2 py-1 border border-border-subtle rounded text-sm bg-bg">
            <option value="week">по неделям</option>
            <option value="month">по месяцам</option>
          </select>
          <select value={daysAhead} onChange={(e) => setDaysAhead(+e.target.value)}
                  className="px-2 py-1 border border-border-subtle rounded text-sm bg-bg">
            <option value={30}>30 дней</option>
            <option value={90}>90 дней</option>
            <option value={180}>180 дней</option>
          </select>
          <AskAIButton
            context={{
              type: 'screen', source_page: 'procurement-calendar',
              source_label: 'Календарь поставок',
              metrics: ['total_orders', 'overdue_count', 'upcoming_30d_value_rub'],
            }}
            question="Где риски по поставкам? Что просрочено и насколько?"
          />
        </div>
      </div>

      {s && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Card className="p-3">
            <div className="text-xs text-fg-muted">Всего заказов</div>
            <div className="text-xl font-semibold tabular-nums">{formatNumber(s.total_orders)}</div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-fg-muted">Стоимость</div>
            <div className="text-xl font-semibold tabular-nums">{formatCurrency(s.total_value_rub)}</div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-fg-muted">Просрочено</div>
            <div className={cn('text-xl font-semibold tabular-nums',
              s.overdue_count > 0 ? 'text-rose-700' : 'text-emerald-700')}>
              {formatNumber(s.overdue_count)}
            </div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-fg-muted">Ожидается за 30д</div>
            <div className="text-xl font-semibold tabular-nums">{formatCurrency(s.upcoming_30d_value_rub)}</div>
          </Card>
        </div>
      )}

      <div className="space-y-3">
        {buckets.map((b) => (
          <Card key={b.period} className="p-4">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
              <div className="flex items-center gap-3">
                <span className="font-semibold text-fg">{b.label}</span>
                <span className="text-sm text-fg-muted">{b.orders_count} заказ(ов)</span>
                {Object.entries(b.by_status).map(([st, cnt]) => (
                  <span key={st} className={cn('text-xs px-2 py-0.5 rounded',
                    STATUS_TONE[st] || 'bg-slate-100 text-slate-700')}>
                    {STATUS_LABEL[st] || st}: {cnt}
                  </span>
                ))}
              </div>
              <div className="text-sm tabular-nums font-medium">{formatCurrency(b.total_value_rub)}</div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-fg-muted">
                  <tr>
                    <th className="py-1 px-2 text-left">Ожидается</th>
                    <th className="py-1 px-2 text-left">Поставщик</th>
                    <th className="py-1 px-2 text-left">Товар</th>
                    <th className="py-1 px-2 text-right">Кол-во</th>
                    <th className="py-1 px-2 text-right">Сумма</th>
                    <th className="py-1 px-2 text-center">Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {b.items.map((o) => (
                    <tr key={o.id} className={cn(
                      'border-t border-border-subtle/40',
                      o.overdue_days > 0 && 'bg-rose-50/30',
                    )}>
                      <td className="py-1.5 px-2 font-mono text-xs">
                        {o.expected_date || <span className="text-fg-subtle">—</span>}
                        {o.overdue_days > 0 && (
                          <span className="ml-1 text-rose-700 text-[10px] font-semibold">
                            <AlertTriangle className="w-3 h-3 inline" /> +{o.overdue_days}д
                          </span>
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-xs">{o.supplier_name || '—'}</td>
                      <td className="py-1.5 px-2 max-w-[260px] truncate" title={o.product_name}>
                        {o.product_name}
                        <span className="text-[10px] text-fg-muted ml-1">{o.offer_id}</span>
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">{o.qty}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums">{formatCurrency(o.total_rub)}</td>
                      <td className="py-1.5 px-2 text-center">
                        <span className={cn('text-[10px] px-2 py-0.5 rounded inline-flex items-center gap-1',
                          STATUS_TONE[o.status])}>
                          {o.status === 'received' && <CheckCircle2 className="w-2.5 h-2.5" />}
                          {o.status === 'in_transit' && <Truck className="w-2.5 h-2.5" />}
                          {o.status === 'created' && <Package className="w-2.5 h-2.5" />}
                          {STATUS_LABEL[o.status] || o.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        ))}
        {buckets.length === 0 && (
          <Card className="p-8 text-center text-fg-muted">
            Заказов поставщикам в этом периоде нет.
          </Card>
        )}
      </div>
    </div>
  )
}
