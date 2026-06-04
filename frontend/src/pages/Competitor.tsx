/**
 * /analytics/competitor — конкурентный сигнал по одному SKU.
 *
 * Прямой конкурентной аналитики Ozon не даёт на Premium Plus. Это
 * КОСВЕННЫЕ сигналы: тренды unique_search/view, конверсия, позиция в
 * категории, доля платного трафика, СПП. Если тренд негативный —
 * конкуренты обходят (через цену/трафик/позицию).
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip,
  CartesianGrid, Legend,
} from 'recharts'
import {
  Target, TrendingUp, TrendingDown, Minus, AlertCircle, Loader2, Info,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { AskAIButton } from '@/components/AskAIButton'
import { api } from '@/lib/api'
import { useCabinetStore } from '@/stores/cabinet'
import { formatNumber, formatCurrency, cn } from '@/lib/utils'

interface SignalPoint {
  date: string
  unique_search: number | null
  unique_view: number | null
  view_conversion_pct: number | null
  gmv_rub: number | null
  position_category: number | null
  ad_imp_share_pct: number | null
  spp_pct: number | null
  revenue_rub: number | null
}
interface Trend {
  metric: string
  first_value: number | null
  last_value: number | null
  change_pct: number | null
  direction: 'up' | 'down' | 'flat'
  verdict: string
}
interface Resp {
  product_id: string
  product_name: string | null
  period_from: string
  period_to: string
  series: SignalPoint[]
  trends: Trend[]
  confidence: 'high' | 'medium' | 'low'
  note: string
}

interface Product { id: string; name: string; offer_id: string | null }

export function Competitor() {
  const { selectedCabinetIds } = useCabinetStore()
  const cabinetId = selectedCabinetIds[0]
  const [productId, setProductId] = useState<string | null>(null)
  const [days, setDays] = useState(30)

  const { data: products } = useQuery<Product[]>({
    queryKey: ['competitor-products', cabinetId],
    queryFn: async () => {
      const r = await api.get('/products/')
      const list = (Array.isArray(r.data) ? r.data : r.data.items || []) as Array<Product & { is_archived?: boolean; cabinet_id?: string }>
      return list
        .filter(p => !p.is_archived && (!cabinetId || p.cabinet_id === cabinetId))
        .map(p => ({ id: p.id, name: p.name, offer_id: p.offer_id }))
    },
  })

  const { data, isLoading } = useQuery<Resp>({
    queryKey: ['competitor-signal', productId, days],
    queryFn: async () => (await api.get(`/competitor/signal?product_id=${productId}&days=${days}`)).data,
    enabled: !!productId,
  })

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
            <Target className="w-6 h-6 text-rose-500" />
            Конкурентный сигнал
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            Косвенные сигналы из Premium Plus: тренды поискового интереса,
            конверсии, позиции в категории, доли рекламы. Если падают — конкуренты задавливают.
          </p>
        </div>
        {productId && (
          <AskAIButton
            context={{
              type: 'chart',
              source_page: 'competitor',
              source_label: `Конкуренты — ${data?.product_name || 'SKU'}`,
              metrics: ['unique_search', 'unique_view', 'view_conversion_pct', 'position_category', 'ad_imp_share_pct', 'spp_pct'],
              period: data ? { from: data.period_from, to: data.period_to } : undefined,
              product_id: productId,
              product_name: data?.product_name || undefined,
              cabinet_ids: selectedCabinetIds,
            }}
            question="Где конкуренты нас обходят? Что предлагаешь делать?"
            variant="solid"
          />
        )}
      </div>

      {/* Фильтры */}
      <Card className="p-3 flex flex-wrap items-center gap-3 text-sm">
        <div>
          <label className="text-xs text-fg-muted mr-2">Товар:</label>
          <select
            value={productId || ''}
            onChange={(e) => setProductId(e.target.value || null)}
            className="px-2 py-1 border border-border-subtle rounded text-sm bg-bg min-w-[280px]"
          >
            <option value="">— выберите SKU —</option>
            {(products || []).map(p => (
              <option key={p.id} value={p.id}>
                {p.name?.slice(0, 60)} {p.offer_id && `(${p.offer_id})`}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-fg-muted mr-2">Период:</label>
          <select value={days} onChange={(e) => setDays(+e.target.value)}
                  className="px-2 py-1 border border-border-subtle rounded text-sm bg-bg">
            <option value={7}>7 дней</option>
            <option value={14}>14 дней</option>
            <option value={30}>30 дней</option>
            <option value={90}>90 дней</option>
          </select>
        </div>
      </Card>

      {!productId && (
        <Card className="p-6 text-center text-sm text-fg-muted">
          Выбери SKU чтобы посмотреть конкурентный сигнал.
        </Card>
      )}

      {productId && isLoading && (
        <div className="text-center py-8"><Loader2 className="w-6 h-6 animate-spin mx-auto text-fg-muted" /></div>
      )}

      {productId && data && (
        <>
          {/* Confidence + note */}
          <Card className={cn('p-3 text-xs border-l-4 flex items-start gap-2',
            data.confidence === 'high' && 'border-emerald-400 bg-emerald-50/30',
            data.confidence === 'medium' && 'border-amber-400 bg-amber-50/30',
            data.confidence === 'low' && 'border-rose-400 bg-rose-50/30',
          )}>
            <Info className="w-4 h-4 mt-0.5 shrink-0" />
            <div>
              <b>Уверенность: {data.confidence}.</b> {data.note}
            </div>
          </Card>

          {/* Тренды — главное */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {data.trends.map((t) => (
              <Card key={t.metric} className="p-4">
                <div className="text-xs text-fg-muted mb-1">{t.metric}</div>
                <div className="flex items-baseline justify-between">
                  <div className="text-2xl font-semibold text-fg tabular-nums">
                    {t.last_value !== null ? formatNumber(t.last_value) : '—'}
                  </div>
                  <div className={cn('flex items-center gap-0.5 text-sm font-medium',
                    t.direction === 'up' && 'text-emerald-600',
                    t.direction === 'down' && 'text-rose-600',
                    t.direction === 'flat' && 'text-fg-muted',
                  )}>
                    {t.direction === 'up' && <TrendingUp className="w-4 h-4" />}
                    {t.direction === 'down' && <TrendingDown className="w-4 h-4" />}
                    {t.direction === 'flat' && <Minus className="w-4 h-4" />}
                    {t.change_pct !== null && `${t.change_pct > 0 ? '+' : ''}${t.change_pct.toFixed(1)}%`}
                  </div>
                </div>
                <div className="text-xs text-fg-muted mt-1">{t.verdict}</div>
              </Card>
            ))}
          </div>

          {/* График поискового интереса + конверсии */}
          <Card className="p-5">
            <h3 className="text-sm font-semibold text-fg mb-3">Поисковый интерес и конверсия</h3>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={data.series}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} unit="%" />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line yAxisId="left" type="monotone" dataKey="unique_search" stroke="#6366f1" strokeWidth={2} dot={false} name="Поиски" />
                <Line yAxisId="left" type="monotone" dataKey="unique_view" stroke="#10b981" strokeWidth={2} dot={false} name="Просмотры" />
                <Line yAxisId="right" type="monotone" dataKey="view_conversion_pct" stroke="#f59e0b" strokeWidth={2} dot={false} name="Конверсия %" />
              </LineChart>
            </ResponsiveContainer>
          </Card>

          {/* Позиция в категории + доля рекламы */}
          <Card className="p-5">
            <h3 className="text-sm font-semibold text-fg mb-3">Позиция и платный трафик</h3>
            <p className="text-xs text-fg-muted mb-2">
              Позиция: ниже = хуже (1 — топ). Доля рекламы: чем выше — тем больше платим чтобы держаться.
            </p>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={data.series}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis yAxisId="left" tick={{ fontSize: 11 }} reversed />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} unit="%" />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line yAxisId="left" type="monotone" dataKey="position_category" stroke="#ef4444" strokeWidth={2} dot={false} name="Позиция в категории" />
                <Line yAxisId="right" type="monotone" dataKey="ad_imp_share_pct" stroke="#8b5cf6" strokeWidth={2} dot={false} name="Доля рекламы %" />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        </>
      )}
    </div>
  )
}
