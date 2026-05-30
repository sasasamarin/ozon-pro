/**
 * «Объяснение дня» — детерминированный разбор почему именно в этот день
 * метрики такие. БЕЗ AI: реклама / цена / остаток / конверсии vs средние.
 */
import { useQuery } from '@tanstack/react-query'
import { X, AlertTriangle, TrendingDown, Package, Megaphone, Tag, CheckCircle2, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'

interface DayMetrics {
  impressions: number
  impressions_search: number
  card_visits: number
  orders: number
  revenue: number
  delivered: number
  returns: number
  cancellations: number
  avg_sold_price: number | null
  seller_price: number | null
  price_dropped_pct: number | null
  avg_customer_price?: number | null     // средняя customer_price этого дня
  customer_spp_pct?: number | null       // СПП покупателя в %
  ad_impressions: number
  ad_clicks: number
  ad_orders: number
  ad_revenue: number
  ad_spend: number
  ad_drr_pct: number | null
  stock_total: number
  stockout: boolean
  cr_search_to_card_pct: number | null
  cr_card_to_order_pct: number | null
}

interface DayFactor {
  type: string
  severity: 'high' | 'medium' | 'low' | 'info'
  title: string
  text: string
}

interface DayExplanation {
  date: string
  product_id: string | null
  product_name: string | null
  day: DayMetrics
  period_avg: Record<string, number>
  period_median: Record<string, number>
  z_scores: Record<string, number | null>
  factors: DayFactor[]
  summary: string
}

const FACTOR_ICON: Record<string, typeof AlertTriangle> = {
  stockout: Package,
  stock_ok: Package,
  ads_off: Megaphone,
  high_drr: Megaphone,
  price_drop: Tag,
  price_ok: Tag,
  customer_spp: Tag,
  impressions_drop: TrendingDown,
  cr_drop: TrendingDown,
  normal: CheckCircle2,
}

const SEVERITY_CLS: Record<string, string> = {
  high: 'border-rose-200 bg-rose-50 text-rose-900',
  medium: 'border-amber-200 bg-amber-50 text-amber-900',
  low: 'border-slate-200 bg-slate-50 text-slate-900',
  info: 'border-blue-200 bg-blue-50 text-blue-900',
}

function MetricRow({ label, day, avg, z, fmt = 'num' }: {
  label: string
  day: number | null | undefined
  avg: number | null | undefined
  z: number | null | undefined
  fmt?: 'num' | 'pct' | 'rub'
}) {
  const format = (v: number | null | undefined) => {
    if (v == null) return '—'
    if (fmt === 'pct') return `${v.toFixed(2)}%`
    if (fmt === 'rub') return formatCurrency(v)
    return formatNumber(v)
  }
  const zColor =
    z == null ? 'text-fg-subtle' :
    z <= -1.5 ? 'text-rose-700 font-semibold' :
    z <= -0.8 ? 'text-amber-700' :
    z >= 1.5 ? 'text-emerald-700 font-semibold' :
    z >= 0.8 ? 'text-emerald-600' :
    'text-fg-subtle'
  return (
    <tr className="border-b border-border-subtle/40 last:border-0">
      <td className="py-2 text-fg-muted">{label}</td>
      <td className="py-2 text-right tabular-nums font-semibold text-fg">{format(day)}</td>
      <td className="py-2 text-right tabular-nums text-fg-muted">{format(avg)}</td>
      <td className={cn('py-2 text-right tabular-nums', zColor)}>
        {z == null ? '—' : (z > 0 ? `+${z}` : `${z}`)}σ
      </td>
    </tr>
  )
}

export function DayExplanationDrawer({
  productId,
  date,
  cabinetIds,
  open,
  onClose,
}: {
  productId: string | null
  date: string | null
  cabinetIds?: string[]
  open: boolean
  onClose: () => void
}) {
  const { data, isLoading, error } = useQuery<DayExplanation>({
    queryKey: ['day-explanation', productId, date, cabinetIds],
    enabled: open && !!date,
    queryFn: async () => {
      const p = new URLSearchParams()
      p.append('date', date!)
      if (productId) p.append('product_id', productId)
      if (cabinetIds) cabinetIds.forEach((id) => p.append('cabinet_ids', id))
      return (await api.get(`/analytics/day-explanation/?${p.toString()}`)).data
    },
  })

  if (!open) return null

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-fg/20 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="fixed right-0 top-0 z-50 h-full w-full max-w-xl bg-bg border-l border-border-subtle shadow-elev overflow-y-auto">
        <div className="sticky top-0 bg-bg z-10 px-6 py-4 border-b border-border-subtle flex items-center justify-between">
          <div>
            <div className="text-xs text-fg-muted uppercase tracking-wider">Объяснение дня</div>
            <h2 className="text-xl font-semibold text-fg mt-0.5">
              {date ? new Date(date).toLocaleDateString('ru', { day: '2-digit', month: 'long', year: 'numeric' }) : ''}
            </h2>
            {data?.product_name && (
              <p className="text-sm text-fg-muted mt-1 line-clamp-1">{data.product_name}</p>
            )}
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-bg-subtle rounded text-fg-muted hover:text-fg">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-5">
          {isLoading && (
            <div className="py-12 flex justify-center text-fg-muted">
              <Loader2 className="w-5 h-5 animate-spin" />
            </div>
          )}
          {error && (
            <div className="py-6 text-rose-700 text-sm">Не удалось загрузить данные дня</div>
          )}

          {data && (
            <>
              {/* Summary */}
              <div className="p-4 rounded-lg bg-bg-subtle border border-border-subtle">
                <p className="text-sm text-fg leading-relaxed">{data.summary}</p>
              </div>

              {/* Подсказка про per-product режим (фактор цены/остатка считается для одного товара) */}
              {!data.product_id && (
                <div className="p-3 rounded-lg bg-blue-50 border border-blue-200 text-xs text-blue-900 leading-relaxed">
                  <strong>Подсказка:</strong> сейчас показан агрегат по всем товарам. Чтобы увидеть факторы
                  <span className="font-semibold"> Цена</span> и
                  <span className="font-semibold"> Остаток</span> — выбери один товар в фильтре товаров на воронке.
                </div>
              )}

              {/* Факторы */}
              <div>
                <h3 className="text-xs font-medium text-fg-muted uppercase tracking-wider mb-2">
                  Факторы ({data.factors.length})
                </h3>
                <div className="space-y-2">
                  {data.factors.map((f, i) => {
                    const Icon = FACTOR_ICON[f.type] || AlertTriangle
                    return (
                      <div key={i} className={cn(
                        'p-3 rounded-lg border flex gap-3',
                        SEVERITY_CLS[f.severity] || SEVERITY_CLS.info,
                      )}>
                        <Icon className="w-5 h-5 shrink-0 mt-0.5" />
                        <div>
                          <div className="font-semibold text-sm">{f.title}</div>
                          <p className="text-sm mt-1 opacity-90">{f.text}</p>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Метрики дня vs средние */}
              <div>
                <h3 className="text-xs font-medium text-fg-muted uppercase tracking-wider mb-2">
                  Метрики дня vs средние за период
                </h3>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-fg-subtle uppercase">
                      <th className="text-left py-1.5 font-medium">метрика</th>
                      <th className="text-right py-1.5 font-medium">день</th>
                      <th className="text-right py-1.5 font-medium">среднее</th>
                      <th className="text-right py-1.5 font-medium" title="z-score: σ от среднего. Чем больше отклонение — тем сильнее аномалия.">отклонение</th>
                    </tr>
                  </thead>
                  <tbody>
                    <MetricRow label="Показы всего" day={data.day.impressions} avg={data.period_avg.impressions} z={data.z_scores.impressions} />
                    <MetricRow label="Посещения карточки" day={data.day.card_visits} avg={data.period_avg.card_visits} z={data.z_scores.card_visits} />
                    <MetricRow label="Заказы" day={data.day.orders} avg={data.period_avg.orders} z={data.z_scores.orders} />
                    <MetricRow label="Выручка" day={data.day.revenue} avg={data.period_avg.revenue} z={data.z_scores.revenue} fmt="rub" />
                    <MetricRow label="CR показ→карточка" day={data.day.cr_search_to_card_pct} avg={data.period_avg.cr_search_to_card_pct} z={data.z_scores.cr_search_to_card_pct} fmt="pct" />
                    <MetricRow label="CR карточка→заказ" day={data.day.cr_card_to_order_pct} avg={data.period_avg.cr_card_to_order_pct} z={data.z_scores.cr_card_to_order_pct} fmt="pct" />
                  </tbody>
                </table>
                <p className="text-[11px] text-fg-subtle mt-2">
                  Средние — за последние 28 дней без выбранного дня. Отклонение в σ: ≤-1.5σ — аномалия (вниз), ≥+1.5σ — аномалия (вверх).
                </p>
              </div>

              {/* Реклама дня */}
              <div>
                <h3 className="text-xs font-medium text-fg-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                  <Megaphone className="w-3.5 h-3.5" /> Реклама
                </h3>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="p-2.5 rounded bg-bg-subtle">
                    <div className="text-[11px] text-fg-muted">Расход</div>
                    <div className="font-semibold tabular-nums">{formatCurrency(data.day.ad_spend)}</div>
                  </div>
                  <div className="p-2.5 rounded bg-bg-subtle">
                    <div className="text-[11px] text-fg-muted">Заказы рекл.</div>
                    <div className="font-semibold tabular-nums">{formatNumber(data.day.ad_orders)}</div>
                  </div>
                  <div className="p-2.5 rounded bg-bg-subtle">
                    <div className="text-[11px] text-fg-muted">Показы рекл.</div>
                    <div className="font-semibold tabular-nums">{formatNumber(data.day.ad_impressions)}</div>
                  </div>
                  <div className="p-2.5 rounded bg-bg-subtle">
                    <div className="text-[11px] text-fg-muted">ДРР</div>
                    <div className="font-semibold tabular-nums">
                      {data.day.ad_drr_pct != null ? `${data.day.ad_drr_pct}%` : '—'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Цена + остаток (только для product_id) */}
              {data.product_id && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded-lg border border-border-subtle">
                    <div className="text-xs font-medium text-fg-muted uppercase tracking-wider flex items-center gap-1.5">
                      <Tag className="w-3.5 h-3.5" /> Цена дня
                    </div>
                    <div className="mt-1.5 space-y-1">
                      <div title="Средняя цена продавца (= accruals_for_sale = твоя выручка на единицу).">
                        <div className="text-xs text-fg-muted">Продавцу</div>
                        <div className="text-base font-bold tabular-nums">
                          {data.day.avg_sold_price != null ? formatCurrency(data.day.avg_sold_price) : '—'}
                        </div>
                      </div>
                      {data.day.avg_customer_price != null && (
                        <div className="mt-1.5 pt-1.5 border-t border-border-subtle/40" title="Средняя «оплачено покупателем» с СПП/Ozon-Картой. На выручку не влияет, драйвер спроса.">
                          <div className="text-xs text-blue-700">С СПП покупателю</div>
                          <div className="text-base font-bold tabular-nums text-blue-700">
                            {formatCurrency(data.day.avg_customer_price)}
                            {data.day.customer_spp_pct != null && (
                              <span className="text-[11px] text-blue-500 ml-1">−{data.day.customer_spp_pct}%</span>
                            )}
                          </div>
                        </div>
                      )}
                      {data.day.price_dropped_pct != null && (
                        <div className="text-[11px] text-amber-700 mt-1">
                          Ozon снизил твою цену на {data.day.price_dropped_pct}%
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="p-3 rounded-lg border border-border-subtle">
                    <div className="text-xs font-medium text-fg-muted uppercase tracking-wider flex items-center gap-1.5">
                      <Package className="w-3.5 h-3.5" /> Остаток на конец дня
                    </div>
                    <div className={cn('mt-1.5 text-xl font-bold tabular-nums',
                      data.day.stockout ? 'text-rose-700' : 'text-fg')}>
                      {formatNumber(data.day.stock_total)} шт
                    </div>
                    {data.day.stockout && (
                      <div className="text-xs text-rose-700 mt-1">Стокаут — товара нет</div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </>
  )
}
