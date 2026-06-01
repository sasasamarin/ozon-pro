/**
 * «Статистика товара» — матрица метрик × период для одного SKU.
 * Аналог nepsell. Sticky левый столбец (метрики) + sticky шапка (даты).
 * Режимы: Таблица / График / Раскраска / Excel-экспорт.
 */
import { useState, useMemo, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Loader2, BarChart3, Table as TableIcon, Palette, Download, Plus,
  Trash2, Pin, Check, X, ChevronRight, ChevronDown, Save, Search,
} from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
  Legend, ReferenceLine,
} from 'recharts'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { DateRangeBar } from '@/components/DateRangeBar'

type Interval = 'day' | 'week' | 'month' | 'all'
type Mode = 'table' | 'chart' | 'heatmap'

interface MetricInfo {
  key: string; label: string; group: string; description: string
  source: string; format: 'number' | 'currency' | 'percent' | 'days'; agg: string
}
interface MatrixRow {
  metric: MetricInfo; total: number | null; cells: (number | null)[]
}
interface MatrixResponse {
  product_id: string; product_name: string; offer_id: string
  interval: string
  bucket_labels: string[]; bucket_dates: string[]
  rows: MatrixRow[]
  markers_by_date: Record<string, { id: string; text: string }[]>
}
interface ProductLookup {
  id: string; offer_id: string; ozon_sku: number; name: string; cabinet_name: string
}
interface Template {
  id: string; name: string; metrics: string[]
}

export function ProductStats() {
  const qc = useQueryClient()
  const [productId, setProductId] = useState<string>('')
  const [productSearch, setProductSearch] = useState('')
  const [days, setDays] = useState(30)
  const [interval, setInterval] = useState<Interval>('day')
  const [mode, setMode] = useState<Mode>('table')
  const [selectedMetrics, setSelectedMetrics] = useState<Set<string>>(new Set())
  const [showArchive, setShowArchive] = useState(false)
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
    new Set(['Трафик', 'Заказы', 'Цена', 'Реклама', 'Прогноз', 'Остатки'])
  )
  const [markerPopup, setMarkerPopup] = useState<{ date: string; existing: { id: string; text: string }[] } | null>(null)

  const { data: metrics } = useQuery<MetricInfo[]>({
    queryKey: ['product-stats-metrics'],
    queryFn: async () => (await api.get('/products/stats/metrics')).data,
  })
  const { data: products } = useQuery<ProductLookup[]>({
    queryKey: ['supplies-product-lookup'],  // переиспользуем тот же endpoint
    queryFn: async () => (await api.get('/supplies/lookup/products')).data,
  })
  const { data: templates } = useQuery<Template[]>({
    queryKey: ['metric-templates'],
    queryFn: async () => (await api.get('/products/stats/templates')).data,
  })

  // Дефолтный набор метрик при первой загрузке
  useEffect(() => {
    if (metrics && selectedMetrics.size === 0) {
      // Базовые: показы, клики, заказы, выручка, выкупили, остаток
      setSelectedMetrics(new Set([
        'impressions', 'clicks', 'cart_count', 'orders', 'delivered',
        'revenue', 'seller_price', 'customer_price', 'spp_pct',
        'ad_spend', 'drr', 'stock_warehouse', 'stock_total',
      ]))
    }
  }, [metrics])

  const filteredProducts = useMemo(() => {
    if (!products) return []
    const q = productSearch.toLowerCase()
    return products.filter(p =>
      !q || p.offer_id.toLowerCase().includes(q) || p.name.toLowerCase().includes(q)
    ).slice(0, 50)
  }, [products, productSearch])

  const { data: matrix, isLoading } = useQuery<MatrixResponse>({
    queryKey: ['product-stats-matrix', productId, days, interval, Array.from(selectedMetrics).sort().join(',')],
    queryFn: async () => {
      const params = new URLSearchParams({ product_id: productId, interval, days: String(days) })
      Array.from(selectedMetrics).forEach(m => params.append('metrics_keys', m))
      return (await api.get(`/products/stats/matrix?${params.toString()}`)).data
    },
    enabled: !!productId && selectedMetrics.size > 0,
  })

  // Группы метрик
  const grouped = useMemo(() => {
    const out: Record<string, MetricInfo[]> = {}
    metrics?.forEach(m => {
      (out[m.group] ||= []).push(m)
    })
    return out
  }, [metrics])

  const allKeys = useMemo(() => new Set(metrics?.map(m => m.key) || []), [metrics])

  const toggleMetric = (k: string) => {
    setSelectedMetrics(prev => {
      const next = new Set(prev)
      next.has(k) ? next.delete(k) : next.add(k)
      return next
    })
  }

  const exportExcel = () => {
    if (!matrix) return
    const rows: string[] = []
    rows.push(['Метрика', 'Весь период', ...matrix.bucket_labels].join('\t'))
    matrix.rows.forEach(r => {
      const cells = [
        r.metric.label,
        formatVal(r.total, r.metric.format),
        ...r.cells.map(c => formatVal(c, r.metric.format)),
      ]
      rows.push(cells.join('\t'))
    })
    const csv = rows.join('\n')
    const blob = new Blob([csv], { type: 'text/tab-separated-values;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `stats_${matrix.offer_id}_${matrix.interval}.tsv`
    a.click()
  }

  // Z-score per row для heatmap
  const heatmapColor = (val: number | null, cells: (number | null)[]): string => {
    if (val == null) return ''
    const nums = cells.filter((v): v is number => v != null)
    if (nums.length < 3) return ''
    const mean = nums.reduce((a, b) => a + b, 0) / nums.length
    const variance = nums.reduce((a, b) => a + (b - mean) ** 2, 0) / nums.length
    const sd = Math.sqrt(variance)
    if (sd === 0) return ''
    const z = (val - mean) / sd
    if (z > 1.5) return 'bg-emerald-200'
    if (z > 0.5) return 'bg-emerald-100'
    if (z < -1.5) return 'bg-rose-200'
    if (z < -0.5) return 'bg-rose-100'
    return ''
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Статистика товара</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          Матрица метрик × период по одному SKU. 45 метрик · 4 интервала · маркеры дней.
        </p>
      </div>

      {/* Селектор товара + период + интервал */}
      <Card className="p-3">
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-[260px]">
            <label className="text-[10px] text-fg-muted uppercase block mb-1">Товар</label>
            <ProductCombo
              value={productId} onChange={setProductId}
              search={productSearch} setSearch={setProductSearch}
              options={filteredProducts}
            />
          </div>
          <div>
            <label className="text-[10px] text-fg-muted uppercase block mb-1">Интервал</label>
            <div className="flex gap-1">
              {(['day', 'week', 'month', 'all'] as Interval[]).map(i => (
                <button key={i} onClick={() => setInterval(i)}
                        className={cn(
                          'px-3 py-1.5 rounded-md text-sm border transition-colors',
                          interval === i
                            ? 'border-fg bg-fg text-bg'
                            : 'border-border-subtle text-fg-muted hover:bg-bg-subtle',
                        )}>
                  {i === 'day' ? 'Дни' : i === 'week' ? 'Недели' : i === 'month' ? 'Месяцы' : 'Весь'}
                </button>
              ))}
            </div>
          </div>
          <DateRangeBar days={days} onChange={setDays} />
        </div>
      </Card>

      {/* Режимы + Excel */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1 border border-border-subtle rounded-md p-0.5">
          {([
            ['table', TableIcon, 'Таблица'],
            ['chart', BarChart3, 'График'],
            ['heatmap', Palette, 'Раскраска'],
          ] as const).map(([k, Icon, label]) => (
            <button key={k} onClick={() => setMode(k)}
                    className={cn(
                      'inline-flex items-center gap-1 px-3 py-1.5 rounded text-sm',
                      mode === k ? 'bg-fg text-bg' : 'text-fg-muted hover:bg-bg-subtle',
                    )}>
              <Icon className="size-3.5" /> {label}
            </button>
          ))}
        </div>
        <button onClick={exportExcel} disabled={!matrix}
                className="inline-flex items-center gap-1 px-3 py-1.5 border border-border-subtle rounded-md text-sm text-fg-muted hover:bg-bg-subtle disabled:opacity-50">
          <Download className="size-3.5" /> Excel
        </button>
      </div>

      {/* Контент */}
      {!productId ? (
        <Card className="p-12 text-center text-fg-muted">Выбери товар из списка</Card>
      ) : isLoading ? (
        <div className="flex justify-center py-12"><Loader2 className="size-6 animate-spin" /></div>
      ) : !matrix ? null : (
        <div className="grid grid-cols-12 gap-3">
          {/* Селектор метрик */}
          <Card className="col-span-3 p-3 max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-medium text-fg uppercase">Метрики</h3>
              <div className="flex gap-1 text-[10px]">
                <button onClick={() => setSelectedMetrics(new Set(allKeys))}
                        className="text-accent hover:underline">все</button>
                <span className="text-fg-muted">/</span>
                <button onClick={() => setSelectedMetrics(new Set())}
                        className="text-fg-muted hover:underline">очистить</button>
              </div>
            </div>
            {/* Шаблоны */}
            <TemplatesPanel
              templates={templates || []}
              selected={selectedMetrics}
              onApply={(t) => setSelectedMetrics(new Set(t.metrics))}
              onSave={async (name) => {
                await api.post('/products/stats/templates', {
                  name, metrics: Array.from(selectedMetrics),
                })
                qc.invalidateQueries({ queryKey: ['metric-templates'] })
              }}
              onDelete={async (id) => {
                await api.delete(`/products/stats/templates/${id}`)
                qc.invalidateQueries({ queryKey: ['metric-templates'] })
              }}
            />
            {/* Группы */}
            {Object.entries(grouped).map(([group, items]) => (
              <div key={group} className="mb-2">
                <button onClick={() => {
                  const next = new Set(expandedGroups)
                  next.has(group) ? next.delete(group) : next.add(group)
                  setExpandedGroups(next)
                }}
                  className="w-full flex items-center justify-between text-xs font-medium text-fg-muted hover:text-fg py-1">
                  <span className="flex items-center gap-1">
                    {expandedGroups.has(group)
                      ? <ChevronDown className="size-3" />
                      : <ChevronRight className="size-3" />}
                    {group}
                  </span>
                  <span className="text-[10px]">
                    {items.filter(m => selectedMetrics.has(m.key)).length}/{items.length}
                  </span>
                </button>
                {expandedGroups.has(group) && items.map(m => (
                  <label key={m.key} className="flex items-start gap-1.5 py-0.5 text-xs cursor-pointer hover:bg-bg-subtle/30 px-1 rounded"
                         title={m.description}>
                    <input type="checkbox" checked={selectedMetrics.has(m.key)}
                           onChange={() => toggleMetric(m.key)}
                           className="mt-0.5" />
                    <span className="flex-1">
                      {m.label}
                      {m.source === 'model' && <span className="ml-1 text-[9px] text-amber-700">оценка</span>}
                    </span>
                  </label>
                ))}
              </div>
            ))}
          </Card>

          {/* Матрица / график */}
          <Card className="col-span-9 p-0 overflow-hidden">
            {mode === 'chart' ? (
              <ChartMode matrix={matrix} />
            ) : (
              <MatrixTable
                matrix={matrix} mode={mode} heatmapColor={heatmapColor}
                onMarkerClick={(date) => setMarkerPopup({
                  date,
                  existing: matrix.markers_by_date[date] || [],
                })}
              />
            )}
          </Card>
        </div>
      )}

      {markerPopup && (
        <MarkerPopup
          date={markerPopup.date}
          existing={markerPopup.existing}
          productId={productId}
          onClose={() => setMarkerPopup(null)}
          onChanged={() => {
            qc.invalidateQueries({ queryKey: ['product-stats-matrix'] })
          }}
        />
      )}
    </div>
  )
}

// =================== sub-components ====================

function ProductCombo({ value, onChange, search, setSearch, options }: {
  value: string; onChange: (v: string) => void
  search: string; setSearch: (v: string) => void
  options: ProductLookup[]
}) {
  const [open, setOpen] = useState(false)
  const selected = options.find(o => o.id === value)
  return (
    <div className="relative">
      <div onClick={() => setOpen(!open)}
           className="px-3 py-1.5 border border-border-subtle rounded-md text-sm bg-bg cursor-pointer min-w-[280px] flex items-center gap-2">
        <Search className="size-3.5 text-fg-muted" />
        {selected
          ? <span className="truncate flex-1"><b>{selected.offer_id}</b> · {selected.name.slice(0, 35)}</span>
          : <span className="text-fg-muted">— выбери товар —</span>}
      </div>
      {open && (
        <div className="absolute top-full left-0 z-10 mt-1 w-96 max-h-80 overflow-y-auto bg-bg border border-border-subtle rounded-md shadow-lg">
          <input value={search} onChange={(e) => setSearch(e.target.value)}
                 placeholder="поиск по offer_id / названию…"
                 className="w-full px-3 py-2 border-b border-border-subtle text-sm outline-none" autoFocus />
          {options.map(o => (
            <div key={o.id} onClick={() => { onChange(o.id); setOpen(false) }}
                 className="px-3 py-1.5 text-sm hover:bg-bg-subtle cursor-pointer border-b border-border-subtle/30">
              <div className="font-medium">{o.offer_id}</div>
              <div className="text-xs text-fg-muted">{o.name} · {o.cabinet_name}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function MatrixTable({ matrix, mode, heatmapColor, onMarkerClick }: {
  matrix: MatrixResponse; mode: Mode
  heatmapColor: (v: number | null, cells: (number | null)[]) => string
  onMarkerClick: (date: string) => void
}) {
  return (
    <div className="overflow-auto max-h-[75vh]">
      <table className="text-xs border-collapse">
        <thead>
          <tr className="bg-bg-subtle">
            <th className="sticky left-0 top-0 z-20 bg-bg-subtle px-3 py-2 text-left border-r border-border-subtle min-w-[200px]">
              Метрика
            </th>
            <th className="sticky top-0 z-10 bg-bg-subtle px-2 py-2 text-right border-r border-border-subtle min-w-[90px]">
              Весь период
            </th>
            {matrix.bucket_labels.map((label, i) => {
              const dateIso = matrix.bucket_dates[i]
              const markers = matrix.markers_by_date[dateIso] || []
              return (
                <th key={i}
                    onClick={() => onMarkerClick(dateIso)}
                    className="sticky top-0 z-10 bg-bg-subtle px-2 py-2 text-center text-fg-muted font-normal min-w-[70px] cursor-pointer hover:bg-bg-subtle/70 whitespace-nowrap relative">
                  {label}
                  {markers.length > 0 && (
                    <Pin className="size-3 text-amber-500 inline ml-1" />
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {matrix.rows.map(r => (
            <tr key={r.metric.key} className="border-t border-border-subtle/30 hover:bg-bg-subtle/20">
              <td className="sticky left-0 bg-bg px-3 py-1.5 border-r border-border-subtle whitespace-nowrap"
                  title={r.metric.description}>
                {r.metric.label}
                {r.metric.source === 'model' && <span className="ml-1 text-[9px] text-amber-700">оценка</span>}
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums font-medium border-r border-border-subtle/40">
                {formatVal(r.total, r.metric.format)}
              </td>
              {r.cells.map((v, i) => (
                <td key={i}
                    className={cn(
                      'px-2 py-1.5 text-right tabular-nums',
                      mode === 'heatmap' && heatmapColor(v, r.cells),
                    )}>
                  {formatVal(v, r.metric.format)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ChartMode({ matrix }: { matrix: MatrixResponse }) {
  const data = matrix.bucket_dates.map((d, i) => {
    const row: Record<string, number | string> = { date: matrix.bucket_labels[i], dateIso: d }
    matrix.rows.forEach(r => {
      const v = r.cells[i]
      if (v != null) row[r.metric.key] = v
    })
    return row
  })
  const colors = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#84cc16', '#ec4899']
  // Маркеры — вертикальные линии
  const markerDates = Object.keys(matrix.markers_by_date)
  return (
    <div className="p-4 h-[600px]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" />
          <YAxis />
          <Tooltip />
          <Legend />
          {matrix.rows.slice(0, 6).map((r, i) => (
            <Line key={r.metric.key} type="monotone" dataKey={r.metric.key}
                  name={r.metric.label} stroke={colors[i % colors.length]} dot={false} />
          ))}
          {markerDates.map(d => {
            const idx = matrix.bucket_dates.indexOf(d)
            if (idx === -1) return null
            return (
              <ReferenceLine key={d} x={matrix.bucket_labels[idx]}
                             stroke="#f59e0b" strokeDasharray="3 3" />
            )
          })}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function TemplatesPanel({ templates, selected, onApply, onSave, onDelete }: {
  templates: Template[]; selected: Set<string>
  onApply: (t: Template) => void
  onSave: (name: string) => Promise<void>
  onDelete: (id: string) => Promise<void>
}) {
  const [showSave, setShowSave] = useState(false)
  const [name, setName] = useState('')
  return (
    <div className="mb-3 pb-2 border-b border-border-subtle/50">
      <div className="flex flex-wrap gap-1 mb-1">
        {templates.map(t => (
          <div key={t.id} className="inline-flex items-center bg-bg-subtle/40 rounded text-[10px]">
            <button onClick={() => onApply(t)} className="px-2 py-1 hover:text-accent">{t.name}</button>
            <button onClick={() => { if (confirm(`Удалить «${t.name}»?`)) onDelete(t.id) }}
                    className="px-1 text-fg-muted hover:text-rose-600">×</button>
          </div>
        ))}
        <button onClick={() => setShowSave(!showSave)}
                className="inline-flex items-center gap-0.5 px-2 py-1 text-[10px] text-accent border border-accent/30 rounded hover:bg-accent/5">
          <Plus className="size-2.5" /> шаблон
        </button>
      </div>
      {showSave && (
        <div className="flex gap-1 mt-1">
          <input value={name} onChange={(e) => setName(e.target.value)}
                 placeholder="название" className="flex-1 px-2 py-1 text-[10px] border border-border-subtle rounded" />
          <button onClick={async () => {
            if (!name || selected.size === 0) return
            await onSave(name); setName(''); setShowSave(false)
          }}
                  className="px-2 py-1 bg-accent text-white text-[10px] rounded">Сохранить ({selected.size})</button>
        </div>
      )}
    </div>
  )
}

function MarkerPopup({ date, existing, productId, onClose, onChanged }: {
  date: string; existing: { id: string; text: string }[]
  productId: string; onClose: () => void; onChanged: () => void
}) {
  const [text, setText] = useState('')
  const add = useMutation({
    mutationFn: async () =>
      api.post('/products/stats/markers', { product_id: productId, marker_date: date, text }),
    onSuccess: () => { setText(''); onChanged() },
  })
  const del = useMutation({
    mutationFn: async (id: string) => api.delete(`/products/stats/markers/${id}`),
    onSuccess: () => onChanged(),
  })
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
         onClick={onClose}>
      <div className="bg-bg rounded-lg shadow-xl max-w-md w-full p-5"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-start mb-3">
          <h3 className="text-base font-semibold flex items-center gap-2">
            <Pin className="size-4 text-amber-500" /> Маркер · {date}
          </h3>
          <button onClick={onClose} className="text-fg-muted"><X className="size-4" /></button>
        </div>
        {existing.length > 0 && (
          <div className="mb-3 space-y-1">
            {existing.map(m => (
              <div key={m.id} className="flex justify-between gap-2 px-2 py-1 bg-amber-50 rounded text-sm">
                <span className="flex-1">{m.text}</span>
                <button onClick={() => del.mutate(m.id)} className="text-fg-muted hover:text-rose-600">
                  <Trash2 className="size-3" />
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <input value={text} onChange={(e) => setText(e.target.value)}
                 placeholder="что сделал в этот день (поднял ставку, снизил цену…)"
                 className="flex-1 px-3 py-1.5 border border-border-subtle rounded text-sm" />
          <button onClick={() => add.mutate()} disabled={!text || add.isPending}
                  className="px-3 py-1.5 bg-accent text-white rounded text-sm disabled:opacity-50">
            <Save className="size-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}

function formatVal(v: number | null, fmt: string): string {
  if (v == null) return '—'
  if (fmt === 'currency') return formatCurrency(v)
  if (fmt === 'percent') return `${v.toFixed(1)}%`
  if (fmt === 'days') return `${Math.round(v)}д`
  return formatNumber(Math.round(v))
}
