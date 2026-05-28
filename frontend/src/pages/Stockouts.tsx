import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  Image as ImageIcon,
  Loader2,
  ArrowRight,
  Info,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { formatNumber, cn } from '@/lib/utils'
import { useRecommendations, ProductRecommendation } from '@/lib/recommendations'

type SignalFilter = 'all' | 'stockout' | 'reorder_now' | 'ok'

const SIGNAL_META: Record<string, { label: string; tone: 'red' | 'amber' | 'green' }> = {
  stockout: { label: '🔴 Стокаут — опаздываешь', tone: 'red' },
  reorder_now: { label: '🟡 Пора заказывать', tone: 'amber' },
  ok: { label: '🟢 Запас в норме', tone: 'green' },
}

function SignalBadge({ signal }: { signal: string }) {
  const meta = SIGNAL_META[signal] || { label: signal, tone: 'green' as const }
  return (
    <span
      className={cn(
        'text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap',
        meta.tone === 'red' && 'text-rose-700 bg-rose-50',
        meta.tone === 'amber' && 'text-amber-700 bg-amber-50',
        meta.tone === 'green' && 'text-emerald-700 bg-emerald-50',
      )}
    >
      {meta.label}
    </span>
  )
}

function ConfidenceDot({ value }: { value: 'high' | 'medium' | 'low' | null }) {
  if (!value) return null
  const color =
    value === 'high'
      ? 'bg-emerald-500'
      : value === 'medium'
      ? 'bg-amber-500'
      : 'bg-fg-subtle'
  return (
    <span className={cn('inline-block w-1.5 h-1.5 rounded-full ml-1', color)} title={value} />
  )
}

export function Stockouts() {
  const { data, isLoading } = useRecommendations()
  const [filter, setFilter] = useState<SignalFilter>('all')

  const rows = useMemo(() => {
    if (!data) return []
    let r = data.filter((p) => p.procurement)
    if (filter !== 'all') {
      r = r.filter((p) => p.procurement!.signal === filter)
    }
    // sort by days_left ASC (горящие сверху); null/∞ — в конец
    r.sort((a, b) => {
      const da = a.procurement!.days_left
      const db = b.procurement!.days_left
      const va = da == null || !Number.isFinite(da) ? Infinity : da
      const vb = db == null || !Number.isFinite(db) ? Infinity : db
      return va - vb
    })
    return r
  }, [data, filter])

  const counts = useMemo(() => {
    if (!data) return { stockout: 0, reorder_now: 0, ok: 0 }
    return data.reduce(
      (acc, p) => {
        if (!p.procurement) return acc
        const s = p.procurement.signal
        if (s === 'stockout') acc.stockout++
        else if (s === 'reorder_now') acc.reorder_now++
        else if (s === 'ok') acc.ok++
        return acc
      },
      { stockout: 0, reorder_now: 0, ok: 0 },
    )
  }, [data])

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Стокауты</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          Прогноз исчерпания остатков. Цвет показывает срочность.
        </p>
      </div>

      <Card className="p-4 flex items-start gap-3 bg-blue-50/60 border-blue-200/60">
        <Info className="w-5 h-5 text-blue-700 mt-0.5 shrink-0" />
        <div className="text-sm text-blue-900/90">
          <strong>Параметры поставки</strong> (lead_time, MOQ, страховой запас) пока не введены —
          расчёт использует дефолты <span className="font-mono">lead_time = 14 дней</span>,{' '}
          <span className="font-mono">safety = 7 дней</span>,{' '}
          <span className="font-mono">MOQ = 1</span>. Для точного прогноза заполните параметры на странице товара.
        </div>
      </Card>

      {/* Filter tabs */}
      <div className="flex gap-2 flex-wrap">
        {([
          ['all', 'Все', data?.length ?? 0],
          ['stockout', '🔴 Стокаут', counts.stockout],
          ['reorder_now', '🟡 Пора заказывать', counts.reorder_now],
          ['ok', '🟢 В норме', counts.ok],
        ] as Array<[SignalFilter, string, number]>).map(([key, label, n]) => (
          <button
            key={key}
            onClick={() => setFilter(key)}
            className={cn(
              'px-3 py-1.5 rounded-md text-sm border transition-colors',
              filter === key
                ? 'border-fg bg-fg text-bg'
                : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
            )}
          >
            {label} <span className="opacity-60">({formatNumber(n)})</span>
          </button>
        ))}
      </div>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 flex justify-center items-center text-fg-muted">
            <Loader2 className="w-5 h-5 animate-spin mr-2" /> Считаем рекомендации…
          </div>
        ) : rows.length === 0 ? (
          <div className="py-20 flex flex-col items-center text-fg-muted">
            <AlertTriangle className="w-8 h-8 mb-3 text-fg-subtle" />
            <p className="text-sm">Нет товаров под выбранный фильтр</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                  <th className="py-2.5 px-4 font-medium">товар</th>
                  <th className="py-2.5 px-4 font-medium text-right">остаток</th>
                  <th className="py-2.5 px-4 font-medium text-right">скорость/день</th>
                  <th className="py-2.5 px-4 font-medium text-right">дни до конца</th>
                  <th className="py-2.5 px-4 font-medium text-right">точка заказа</th>
                  <th className="py-2.5 px-4 font-medium">статус</th>
                  <th className="py-2.5 px-4 font-medium text-right">заказать</th>
                  <th className="py-2.5 px-4 font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {rows.map((p) => {
                  const pr = p.procurement!
                  const reorderPoint = pr.lead_time_days + pr.safety_stock_days
                  return (
                    <tr
                      key={p.product_id}
                      className={cn(
                        'hover:bg-bg-subtle/50',
                        pr.signal === 'stockout' && 'bg-rose-50/40',
                      )}
                    >
                      <td className="py-2.5 px-4">
                        <div className="flex items-center gap-3 min-w-0">
                          {p.image_url ? (
                            <img
                              src={p.image_url}
                              alt=""
                              className="w-9 h-9 rounded object-cover shrink-0 border border-border-subtle"
                            />
                          ) : (
                            <div className="w-9 h-9 rounded bg-bg-subtle flex items-center justify-center shrink-0">
                              <ImageIcon className="w-4 h-4 text-fg-subtle" />
                            </div>
                          )}
                          <div className="min-w-0">
                            <div className="font-medium text-fg truncate max-w-[320px]">
                              {p.product_name}
                            </div>
                            <div className="text-xs text-fg-muted font-mono truncate">
                              {p.offer_id}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums">
                        {formatNumber(p.current_stock)}
                        {p.in_transit_to_customer > 0 && (
                          <div className="text-[10px] text-fg-subtle">
                            +{p.in_transit_to_customer} в пути
                          </div>
                        )}
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums">
                        {p.velocity.adjusted_daily.toFixed(1)}
                        <ConfidenceDot value={p.velocity.confidence} />
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums">
                        <span
                          className={cn(
                            pr.signal === 'stockout' && 'text-rose-700 font-semibold',
                            pr.signal === 'reorder_now' && 'text-amber-700 font-semibold',
                          )}
                        >
                          {pr.days_left != null && Number.isFinite(pr.days_left)
                            ? pr.days_left.toFixed(0)
                            : '∞'}
                        </span>
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums text-fg-muted">
                        {reorderPoint}
                      </td>
                      <td className="py-2.5 px-4">
                        <SignalBadge signal={pr.signal} />
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums">
                        {pr.recommended_qty > 0 ? (
                          <span className="font-semibold text-fg">{formatNumber(pr.recommended_qty)}</span>
                        ) : (
                          <span className="text-fg-subtle">—</span>
                        )}
                      </td>
                      <td className="py-2.5 px-2">
                        <Link
                          to={`/procurement/forecast?product_id=${p.product_id}`}
                          className="inline-flex items-center text-xs text-fg-muted hover:text-fg"
                        >
                          детали <ArrowRight className="w-3.5 h-3.5 ml-1" />
                        </Link>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
