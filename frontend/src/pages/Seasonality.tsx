/**
 * Сезонность — раздел «Раздел Сезонность» из брифа.
 *
 * Источники (Принцип 4):
 *  - own_sales — своя история SKU (≥365 дней)
 *  - cabinet_category_aggregate — агрегат своих SKU по категории кабинета
 *    (fallback для SKU с малой историей. На Premium Plus рынка нет — был probe).
 *
 * Каждое число имеет source-флаг. Бейдж уверенности (days_history) сверху.
 */
import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts'
import { Calendar, TrendingUp, AlertCircle, Sparkles, Info, ShoppingCart } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { useCabinetStore } from '@/stores/cabinet'
import { formatNumber, cn } from '@/lib/utils'

type Metric = 'orders' | 'buyouts' | 'revenue'
type Granularity = 'month' | 'week'
type SourcePref = 'auto' | 'own' | 'category'

interface ConfidenceBlock {
  days_history: number
  confidence: 'high' | 'medium' | 'low' | 'insufficient'
  note: string
  yoy_full_years: number
}

interface ProfileBucket {
  bucket: number
  value: number
  index: number | null
  years_seen: number
}

interface ProfileResp {
  source: string
  confidence: ConfidenceBlock
  metric: Metric
  granularity: Granularity
  buckets: ProfileBucket[]
  annual_avg: number
  based_on_months?: number
}

interface YoyResp {
  source: string
  confidence: ConfidenceBlock
  metric: Metric
  years: number[]
  series: Array<Record<string, number>>
}

interface DetectItem {
  product_id: string
  name: string | null
  offer_id: string | null
  ozon_sku: number | null
  days_history: number
  confidence: ConfidenceBlock['confidence']
  verdict: 'seasonal' | 'flat' | 'insufficient'
  peak_month: number | null
  amplitude_ratio: number | null
}

interface EventItem {
  id: string
  name: string
  kind: 'holiday' | 'sale' | 'season'
  date_start: string
  date_end: string | null
  note: string
  icon: string
  year?: number
}

const MONTH_NAMES = ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек']
const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']


function ConfidenceBadge({ c }: { c: ConfidenceBlock }) {
  const map = {
    high: { color: 'bg-emerald-50 text-emerald-700 border-emerald-200', label: 'Полноценный анализ' },
    medium: { color: 'bg-amber-50 text-amber-700 border-amber-200', label: '1 год — низкая уверенность' },
    low: { color: 'bg-orange-50 text-orange-700 border-orange-200', label: 'Предварительно' },
    insufficient: { color: 'bg-rose-50 text-rose-700 border-rose-200', label: 'Недостаточно данных' },
  }[c.confidence]
  return (
    <span className={cn('inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs border', map.color)}>
      <Info className="w-3 h-3" />
      <b>{map.label}</b> · {c.days_history} дней истории
    </span>
  )
}


function SourceBadge({ source }: { source: string }) {
  const isOwn = source === 'own_sales'
  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium',
      isOwn ? 'bg-blue-50 text-blue-700' : 'bg-purple-50 text-purple-700',
    )}>
      {isOwn ? '📊 по вашим продажам' : '🗂️ по категории кабинета'}
    </span>
  )
}


export function Seasonality() {
  const { selectedCabinetIds } = useCabinetStore()
  const cabinetId = selectedCabinetIds[0] || null

  const [productId, setProductId] = useState<string | null>(null)
  const [metric, setMetric] = useState<Metric>('buyouts')
  const [granularity, setGranularity] = useState<Granularity>('month')
  const [sourcePref, setSourcePref] = useState<SourcePref>('auto')

  // Список продуктов кабинета — для выбора SKU
  const { data: products } = useQuery<Array<{ id: string; name: string; offer_id: string }>>({
    queryKey: ['seasonality-products', cabinetId],
    queryFn: async () => {
      const params = new URLSearchParams({ archived: 'false', limit: '500' })
      if (cabinetId) params.append('cabinet_ids', cabinetId)
      const r = await api.get(`/products?${params.toString()}`)
      return r.data.items || r.data
    },
    enabled: !!cabinetId,
  })

  const profileQuery = useQuery<ProfileResp>({
    queryKey: ['seasonality-profile', cabinetId, productId, metric, granularity, sourcePref],
    queryFn: async () => {
      const params = new URLSearchParams({
        metric, granularity, source_pref: sourcePref,
      })
      if (productId) params.append('product_id', productId)
      else if (cabinetId) params.append('cabinet_id', cabinetId)
      return (await api.get(`/seasonality/profile?${params.toString()}`)).data
    },
    enabled: !!(cabinetId || productId),
  })

  const yoyQuery = useQuery<YoyResp>({
    queryKey: ['seasonality-yoy', cabinetId, productId, metric, sourcePref],
    queryFn: async () => {
      const params = new URLSearchParams({ metric, source_pref: sourcePref })
      if (productId) params.append('product_id', productId)
      else if (cabinetId) params.append('cabinet_id', cabinetId)
      return (await api.get(`/seasonality/yoy?${params.toString()}`)).data
    },
    enabled: !!(cabinetId || productId),
  })

  const detectQuery = useQuery<{ items: DetectItem[] }>({
    queryKey: ['seasonality-detect', cabinetId, metric],
    queryFn: async () => {
      const params = new URLSearchParams({ metric })
      if (cabinetId) params.append('cabinet_id', cabinetId)
      return (await api.get(`/seasonality/detect?${params.toString()}`)).data
    },
    enabled: !!cabinetId,
  })

  const eventsQuery = useQuery<EventItem[]>({
    queryKey: ['seasonality-events'],
    queryFn: async () => (await api.get('/seasonality/events')).data,
  })

  const profile = profileQuery.data
  const yoy = yoyQuery.data
  const detect = detectQuery.data?.items || []
  const events = eventsQuery.data || []

  // === Recharts data ===
  const profileChart = useMemo(() => {
    if (!profile) return []
    return profile.buckets.map(b => ({
      label: granularity === 'month' ? MONTH_NAMES[b.bucket - 1] : `Н${b.bucket}`,
      bucket: b.bucket,
      value: b.value,
      index: b.index,
    }))
  }, [profile, granularity])

  const yoyChart = useMemo(() => {
    if (!yoy) return { rows: [], years: [] }
    const xKey = yoy.source === 'own_sales' ? 'doy' : 'month'
    // recharts ожидает плоский массив с series-ключами
    return { rows: yoy.series, years: yoy.years, xKey }
  }, [yoy])

  // Маркеры событий для текущего года на YoY
  const eventMarkers = useMemo(() => {
    if (!yoy || yoy.source !== 'own_sales') return []
    // Convert event dates → day-of-year для текущего года
    const y = new Date().getFullYear()
    return events
      .filter(e => e.kind !== 'season')
      .map(e => {
        const d = new Date(e.date_start)
        const startOfYear = new Date(d.getFullYear(), 0, 0)
        const diff = d.getTime() - startOfYear.getTime()
        const doy = Math.floor(diff / (1000 * 60 * 60 * 24))
        return { doy, name: e.name, icon: e.icon }
      })
      .filter(m => m.doy > 0)
  }, [events, yoy])

  return (
    <div className="space-y-5">
      {/* === Header === */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
            <Calendar className="w-6 h-6 text-fg-muted" />
            Сезонность
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            Когда у каждого товара пик и провал. Источники: <b>свои продажи</b> (требует ≥365 дней) ·
            <b> категория кабинета</b> (fallback для новых SKU).
          </p>
        </div>
      </div>

      {/* === Фильтры === */}
      <Card className="p-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-sm">
          <div>
            <label className="text-xs text-fg-muted block mb-1">Товар</label>
            <select
              value={productId || ''}
              onChange={(e) => setProductId(e.target.value || null)}
              className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg"
            >
              <option value="">Весь кабинет (все SKU)</option>
              {(products || []).map(p => (
                <option key={p.id} value={p.id}>
                  {p.name?.slice(0, 50)} {p.offer_id ? `(${p.offer_id})` : ''}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-fg-muted block mb-1">Метрика</label>
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value as Metric)}
              className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg"
            >
              <option value="buyouts">Выкупы (доставлено)</option>
              <option value="orders">Заказы (все статусы)</option>
              <option value="revenue">Выручка, ₽</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-fg-muted block mb-1">Гранулярность</label>
            <select
              value={granularity}
              onChange={(e) => setGranularity(e.target.value as Granularity)}
              className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg"
            >
              <option value="month">Месяц</option>
              <option value="week">Неделя</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-fg-muted block mb-1">Источник</label>
            <select
              value={sourcePref}
              onChange={(e) => setSourcePref(e.target.value as SourcePref)}
              className="w-full px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg"
            >
              <option value="auto">Авто (свои если ≥365д)</option>
              <option value="own">Только свои</option>
              <option value="category">Только категория кабинета</option>
            </select>
          </div>
        </div>
        {profile && (
          <div className="mt-3 flex items-center gap-3 flex-wrap">
            <ConfidenceBadge c={profile.confidence} />
            <SourceBadge source={profile.source} />
            {profile.confidence.note && (
              <span className="text-xs text-fg-muted italic">{profile.confidence.note}</span>
            )}
          </div>
        )}
      </Card>

      {/* === YoY-график === */}
      <Card className="p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-fg flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-fg-muted" />
            YoY: продажи по годам
          </h2>
          {yoy && <SourceBadge source={yoy.source} />}
        </div>
        {!yoy || yoy.series.length === 0 ? (
          <div className="rounded-md border border-amber-200 bg-amber-50/60 p-3 text-sm text-amber-900 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <div>YoY-данных нет — у выбранной выборки слишком мало истории.</div>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={yoyChart.rows}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis
                dataKey={yoyChart.xKey}
                tick={{ fontSize: 11 }}
                label={{
                  value: yoy.source === 'own_sales' ? 'День года' : 'Месяц',
                  position: 'insideBottom', offset: -5, fontSize: 11,
                }}
              />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(v: number) => formatNumber(v)}
                labelFormatter={(l) => yoy.source === 'own_sales' ? `день ${l}` : `месяц ${l}`}
              />
              <Legend />
              {eventMarkers.map(m => (
                <ReferenceLine
                  key={m.name + m.doy}
                  x={m.doy}
                  stroke="#94a3b8"
                  strokeDasharray="3 3"
                  label={{ value: m.icon, fontSize: 14, position: 'top' }}
                />
              ))}
              {yoy.years.map((y, i) => (
                <Line
                  key={y}
                  type="monotone"
                  dataKey={String(y)}
                  stroke={COLORS[i % COLORS.length]}
                  strokeWidth={2}
                  dot={false}
                  name={String(y)}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* === Профиль === */}
      <Card className="p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-fg flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-fg-muted" />
            Сезонный профиль ({granularity === 'month' ? 'по месяцам' : 'по неделям'})
          </h2>
          {profile && <SourceBadge source={profile.source} />}
        </div>
        <p className="text-xs text-fg-muted mb-3">
          Индекс = продажи периода / среднегодовые. <b>&gt;1</b> = пик, <b>&lt;1</b> = провал.
        </p>
        {profile && profile.buckets.length > 0 ? (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={profileChart}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(v: number, name: string) => name === 'index' ? v?.toFixed(2) : formatNumber(v)}
              />
              <ReferenceLine y={1} stroke="#64748b" strokeDasharray="2 2" label={{ value: 'среднее', fontSize: 10 }} />
              <Bar dataKey="index" name="Индекс" fill="#6366f1">
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-fg-muted">Нет данных для построения профиля.</p>
        )}
      </Card>

      {/* === Автодетект таблица === */}
      <Card className="p-5">
        <h2 className="text-base font-semibold text-fg mb-3 flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-fg-muted" />
          Автодетект сезонности по SKU
        </h2>
        <p className="text-xs text-fg-muted mb-3">
          Сезонный = амплитуда max/min индекс &gt; 1.5 И ≥365 дней истории.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-fg-muted border-b border-border-subtle">
              <tr>
                <th className="py-2 px-2 text-left">Товар</th>
                <th className="py-2 px-2 text-right">История</th>
                <th className="py-2 px-2 text-center">Вердикт</th>
                <th className="py-2 px-2 text-center">Пик</th>
                <th className="py-2 px-2 text-right">Амплитуда</th>
              </tr>
            </thead>
            <tbody>
              {detect.map(item => (
                <tr key={item.product_id} className="border-b border-border-subtle/40 hover:bg-bg-subtle/30">
                  <td className="py-2 px-2">
                    <div className="text-fg">{item.name?.slice(0, 60)}</div>
                    <div className="text-xs text-fg-muted">{item.offer_id} · sku {item.ozon_sku}</div>
                  </td>
                  <td className="py-2 px-2 text-right text-fg-muted">{item.days_history}д</td>
                  <td className="py-2 px-2 text-center">
                    {item.verdict === 'seasonal' && <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 rounded text-xs">🌊 сезонный</span>}
                    {item.verdict === 'flat'     && <span className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs">📏 ровный</span>}
                    {item.verdict === 'insufficient' && <span className="px-2 py-0.5 bg-rose-50 text-rose-700 rounded text-xs">⚠️ мало данных</span>}
                  </td>
                  <td className="py-2 px-2 text-center font-mono">
                    {item.peak_month ? MONTH_NAMES[item.peak_month - 1] : '—'}
                  </td>
                  <td className="py-2 px-2 text-right tabular-nums">
                    {item.amplitude_ratio ? `×${item.amplitude_ratio.toFixed(2)}` : '—'}
                  </td>
                </tr>
              ))}
              {detect.length === 0 && (
                <tr><td colSpan={5} className="py-6 text-center text-fg-muted">Нет SKU с продажами.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* === Календарь событий === */}
      <Card className="p-5">
        <h2 className="text-base font-semibold text-fg mb-3 flex items-center gap-2">
          <ShoppingCart className="w-4 h-4 text-fg-muted" />
          Календарь событий
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-sm">
          {events.map(e => (
            <div key={e.id} className="flex items-start gap-2 p-2 rounded border border-border-subtle">
              <span className="text-xl">{e.icon}</span>
              <div className="min-w-0">
                <div className="font-medium text-fg truncate">{e.name}</div>
                <div className="text-xs text-fg-muted">
                  {e.date_start}{e.date_end ? ` — ${e.date_end}` : ''}
                </div>
                <div className="text-xs text-fg-muted truncate">{e.note}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
