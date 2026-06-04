/**
 * Дашборд: Конструктор графиков (custom graph cards) — аналог nepsell.
 *
 * Шапка-фильтры (общие): кабинеты × период × интервал × индикатор актуальности.
 * Сетка карточек: drag-reorder, ✏️ редактирование (метрики + ось + цвет + тип),
 * 🗑 удалить, + добавить. Авто-сохранение через PUT /dashboard/builder/layout.
 *
 * Две оси Y: автоматически по типу единицы (₽/% разные), с переопределением в редакторе.
 */
import { useState, useMemo, useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  LayoutDashboard, Plus, Edit2, Trash2, Loader2, GripVertical, X, Save,
  Search, AlertCircle,
} from 'lucide-react'
import {
  LineChart, Line, BarChart, Bar, ComposedChart, XAxis, YAxis, Tooltip,
  CartesianGrid, ResponsiveContainer, Legend,
} from 'recharts'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { DateRangeBar } from '@/components/DateRangeBar'
import { useCabinetStore } from '@/stores/cabinet'
import { AskAIButton } from '@/components/AskAIButton'

type Interval = 'day' | 'week' | 'month'
type Axis = 'left' | 'right'
type ChartType = 'line' | 'bar'
type MetricFormat = 'number' | 'currency' | 'percent' | 'days'

interface MetricInfo {
  key: string; label: string; group: string; description: string
  source: string; format: MetricFormat; agg: string
}
interface CardMetric {
  key: string; axis: Axis; color: string; chartType?: ChartType
}
interface CardConfig {
  id: string; title: string
  chartType: ChartType  // default for metrics that don't override
  metrics: CardMetric[]
}
interface Layout {
  id: string; scope: string; name: string | null; cards: CardConfig[]
}
interface SeriesPoint { date: string; values: Record<string, number | null> }
interface SeriesResponse { interval: string; points: SeriesPoint[] }

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#84cc16', '#ec4899']

// Авто-ось по формату метрики
function autoAxis(format: MetricFormat, existingMetrics: CardMetric[], allMetrics: MetricInfo[]): Axis {
  // Если уже есть метрика этого формата — наследуем её ось
  for (const em of existingMetrics) {
    const m = allMetrics.find(x => x.key === em.key)
    if (m && m.format === format) return em.axis
  }
  // Иначе: % и days — справа, ₽ и number — слева
  if (format === 'percent' || format === 'days') return 'right'
  return 'left'
}

export function DashboardBuilder() {
  const qc = useQueryClient()
  const { selectedCabinetIds } = useCabinetStore()
  const [days, setDays] = useState(28)
  const [dateFrom, setDateFrom] = useState<string | null>(null)
  const [dateTo, setDateTo] = useState<string | null>(null)
  const [interval, setIntervalState] = useState<Interval>('day')
  const [editingCardId, setEditingCardId] = useState<string | null>(null)

  const { data: metrics } = useQuery<MetricInfo[]>({
    queryKey: ['product-stats-metrics'],
    queryFn: async () => (await api.get('/products/stats/metrics')).data,
  })

  const { data: layout } = useQuery<Layout>({
    queryKey: ['dashboard-layout'],
    queryFn: async () => (await api.get('/dashboard/builder/layout?scope=cabinet')).data,
  })

  const saveLayout = useMutation({
    mutationFn: async (newCards: CardConfig[]) =>
      api.put('/dashboard/builder/layout', { scope: 'cabinet', cards: newCards }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard-layout'] }),
  })

  const cards = layout?.cards || []
  const editingCard = cards.find(c => c.id === editingCardId)

  const addCard = () => {
    const newCard: CardConfig = {
      id: `card-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      title: 'Новая карточка',
      chartType: 'line',
      metrics: [],
    }
    const next = [...cards, newCard]
    saveLayout.mutate(next)
    setEditingCardId(newCard.id)
  }

  const updateCard = (id: string, patch: Partial<CardConfig>) => {
    const next = cards.map(c => c.id === id ? { ...c, ...patch } : c)
    saveLayout.mutate(next)
  }

  const deleteCard = (id: string) => {
    if (!confirm('Удалить карточку?')) return
    saveLayout.mutate(cards.filter(c => c.id !== id))
  }

  // Drag-reorder
  const dragId = useRef<string | null>(null)
  const onDragStart = (id: string) => { dragId.current = id }
  const onDragOver = (e: React.DragEvent) => e.preventDefault()
  const onDrop = (targetId: string) => {
    if (!dragId.current || dragId.current === targetId) return
    const from = cards.findIndex(c => c.id === dragId.current)
    const to = cards.findIndex(c => c.id === targetId)
    if (from < 0 || to < 0) return
    const next = [...cards]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    saveLayout.mutate(next)
    dragId.current = null
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="inline-flex items-center gap-2 text-xs text-fg-muted bg-bg-subtle/40 px-2 py-1 rounded">
            <LayoutDashboard className="size-3" /> Конструктор графиков
          </div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight mt-2">Дашборд</h1>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div>
            <label className="text-[10px] text-fg-muted uppercase block mb-1">Интервал</label>
            <div className="flex gap-1">
              {(['day', 'week', 'month'] as Interval[]).map(i => (
                <button key={i} onClick={() => setIntervalState(i)}
                        className={cn(
                          'px-3 py-1.5 rounded-md text-sm border',
                          interval === i ? 'border-fg bg-fg text-bg'
                                          : 'border-border-subtle text-fg-muted hover:bg-bg-subtle',
                        )}>
                  {i === 'day' ? 'День' : i === 'week' ? 'Неделя' : 'Месяц'}
                </button>
              ))}
            </div>
          </div>
          <DateRangeBar days={days}
            onChange={(r) => { setDays(r.days); setDateFrom(r.dateFrom); setDateTo(r.dateTo) }} />
          <AskAIButton
            context={{
              type: 'screen',
              source_page: 'dashboard',
              source_label: 'Дашборд (карточки метрик)',
              metrics: cards.flatMap(c => c.metrics.map(m => m.key)).slice(0, 20),
              period: dateFrom && dateTo
                ? { from: dateFrom, to: dateTo }
                : undefined,
              cabinet_ids: selectedCabinetIds,
            }}
            question="Что главное на дашборде за период? Где аномалии?"
            variant="solid"
          />
          <button onClick={addCard}
                  className="inline-flex items-center gap-1 px-3 py-1.5 bg-accent text-white rounded-md text-sm font-medium hover:bg-accent-hover">
            <Plus className="size-4" /> Карточка
          </button>
        </div>
      </div>

      {cards.length === 0 ? (
        <Card className="p-12 text-center">
          <LayoutDashboard className="size-12 mx-auto text-fg-muted/40" />
          <p className="text-fg-muted mt-3">Дашборд пуст. Нажми «+ Карточка» и выбери метрики.</p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {cards.map(card => (
            <CardChart
              key={card.id}
              card={card}
              metrics={metrics || []}
              cabinetIds={selectedCabinetIds}
              days={days}
              dateFrom={dateFrom}
              dateTo={dateTo}
              interval={interval}
              onDragStart={onDragStart}
              onDragOver={onDragOver}
              onDrop={onDrop}
              onEdit={() => setEditingCardId(card.id)}
              onDelete={() => deleteCard(card.id)}
            />
          ))}
        </div>
      )}

      {editingCard && (
        <CardEditor
          card={editingCard}
          metrics={metrics || []}
          onSave={(patch) => { updateCard(editingCard.id, patch); setEditingCardId(null) }}
          onClose={() => setEditingCardId(null)}
        />
      )}
    </div>
  )
}

// ============ Карточка с графиком ============

function CardChart({
  card, metrics, cabinetIds, days, dateFrom, dateTo, interval,
  onDragStart, onDragOver, onDrop, onEdit, onDelete,
}: {
  card: CardConfig
  metrics: MetricInfo[]
  cabinetIds: string[]
  days: number
  dateFrom: string | null
  dateTo: string | null
  interval: Interval
  onDragStart: (id: string) => void
  onDragOver: (e: React.DragEvent) => void
  onDrop: (id: string) => void
  onEdit: () => void
  onDelete: () => void
}) {
  const { data, isLoading } = useQuery<SeriesResponse>({
    queryKey: ['series', card.metrics.map(m => m.key).sort().join(','), days, dateFrom, dateTo, interval, cabinetIds.join(',')],
    queryFn: async () => {
      const params = new URLSearchParams({ interval })
      if (dateFrom && dateTo) {
        params.set('date_from', dateFrom); params.set('date_to', dateTo)
      } else {
        params.set('days', String(days))
      }
      card.metrics.forEach(m => params.append('metrics_keys', m.key))
      cabinetIds.forEach(c => params.append('cabinet_ids', c))
      return (await api.get(`/dashboard/builder/series?${params.toString()}`)).data
    },
    enabled: card.metrics.length > 0,
  })

  const chartData = useMemo(() => {
    if (!data) return []
    return data.points.map(p => ({ date: p.date, ...p.values }))
  }, [data])

  const leftMetrics = card.metrics.filter(m => m.axis === 'left')
  const rightMetrics = card.metrics.filter(m => m.axis === 'right')

  const metricMeta = (k: string) => metrics.find(m => m.key === k)

  return (
    <Card
      draggable
      onDragStart={() => onDragStart(card.id)}
      onDragOver={onDragOver}
      onDrop={() => onDrop(card.id)}
      className="p-4"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <GripVertical className="size-4 text-fg-muted/50 cursor-move shrink-0" />
          <h3 className="text-sm font-medium text-fg truncate">{card.title}</h3>
        </div>
        <div className="flex gap-1 shrink-0">
          <button onClick={onEdit} className="p-1 text-fg-muted hover:text-fg" title="Редактировать">
            <Edit2 className="size-3.5" />
          </button>
          <button onClick={onDelete} className="p-1 text-fg-muted hover:text-rose-600" title="Удалить">
            <Trash2 className="size-3.5" />
          </button>
        </div>
      </div>
      {card.metrics.length === 0 ? (
        <div className="h-64 flex flex-col items-center justify-center text-fg-muted text-sm border-2 border-dashed border-border-subtle rounded">
          <AlertCircle className="size-6 mb-2 opacity-50" />
          Метрики не выбраны. Откройте редактирование.
        </div>
      ) : isLoading ? (
        <div className="h-64 flex items-center justify-center">
          <Loader2 className="size-6 animate-spin text-fg-muted" />
        </div>
      ) : (
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              {leftMetrics.length > 0 && (
                <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
              )}
              {rightMetrics.length > 0 && (
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
              )}
              <Tooltip
                formatter={(v: number, name: string) => {
                  const m = card.metrics.find(cm => metricMeta(cm.key)?.label === name)
                  if (!m) return v
                  const meta = metricMeta(m.key)
                  if (!meta) return v
                  return [
                    meta.format === 'currency' ? formatCurrency(v)
                    : meta.format === 'percent' ? `${v.toFixed(1)}%`
                    : meta.format === 'days' ? `${Math.round(v)} дн`
                    : formatNumber(Math.round(v)),
                    name,
                  ]
                }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {card.metrics.map(m => {
                const meta = metricMeta(m.key)
                if (!meta) return null
                if ((m.chartType ?? card.chartType) === 'bar') {
                  return <Bar key={m.key} dataKey={m.key} name={meta.label}
                              yAxisId={m.axis} fill={m.color} />
                }
                return <Line key={m.key} type="monotone" dataKey={m.key} name={meta.label}
                             yAxisId={m.axis} stroke={m.color} dot={false} strokeWidth={2} />
              })}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}

// ============ Редактор карточки ============

function CardEditor({
  card, metrics, onSave, onClose,
}: {
  card: CardConfig; metrics: MetricInfo[]
  onSave: (patch: Partial<CardConfig>) => void
  onClose: () => void
}) {
  const [title, setTitle] = useState(card.title)
  const [chartType, setChartType] = useState<ChartType>(card.chartType)
  const [metricsList, setMetricsList] = useState<CardMetric[]>(card.metrics)
  const [search, setSearch] = useState('')

  const isSelected = (k: string) => metricsList.some(m => m.key === k)
  const toggleMetric = (m: MetricInfo) => {
    if (isSelected(m.key)) {
      setMetricsList(metricsList.filter(x => x.key !== m.key))
    } else if (metricsList.length < 4) {
      setMetricsList([...metricsList, {
        key: m.key,
        axis: autoAxis(m.format, metricsList, metrics),
        color: COLORS[metricsList.length % COLORS.length],
      }])
    }
  }
  const updateMetric = (k: string, patch: Partial<CardMetric>) => {
    setMetricsList(metricsList.map(m => m.key === k ? { ...m, ...patch } : m))
  }

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return metrics.filter(m =>
      !q || m.label.toLowerCase().includes(q) || m.key.toLowerCase().includes(q)
    )
  }, [metrics, search])

  const grouped = useMemo(() => {
    const out: Record<string, MetricInfo[]> = {}
    filtered.forEach(m => { (out[m.group] ||= []).push(m) })
    return out
  }, [filtered])

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4 overflow-y-auto"
         onClick={onClose}>
      <div className="bg-bg rounded-xl shadow-xl max-w-3xl w-full p-6 my-8"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-4">
          <h2 className="text-lg font-semibold text-fg">Карточка графика</h2>
          <button onClick={onClose} className="text-fg-muted"><X className="size-5" /></button>
        </div>

        <div className="grid grid-cols-12 gap-3 mb-4">
          <div className="col-span-7">
            <label className="text-[10px] text-fg-muted uppercase block mb-1">Заголовок</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)}
                   className="w-full px-3 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
          </div>
          <div className="col-span-5">
            <label className="text-[10px] text-fg-muted uppercase block mb-1">Тип по умолчанию</label>
            <select value={chartType} onChange={(e) => setChartType(e.target.value as ChartType)}
                    className="w-full px-3 py-1.5 border border-border-subtle rounded text-sm bg-bg">
              <option value="line">Линия</option>
              <option value="bar">Столбцы</option>
            </select>
          </div>
        </div>

        {/* Выбранные метрики */}
        {metricsList.length > 0 && (
          <div className="mb-3 space-y-2">
            <div className="text-xs text-fg-muted uppercase">Выбрано ({metricsList.length}/4)</div>
            {metricsList.map(m => {
              const meta = metrics.find(x => x.key === m.key)
              if (!meta) return null
              return (
                <div key={m.key} className="grid grid-cols-12 gap-2 items-center bg-bg-subtle/30 rounded px-2 py-1.5">
                  <div className="col-span-1 flex items-center justify-center">
                    <div className="w-4 h-4 rounded" style={{ backgroundColor: m.color }} />
                  </div>
                  <div className="col-span-4 text-sm">{meta.label}</div>
                  <select value={m.axis}
                          onChange={(e) => updateMetric(m.key, { axis: e.target.value as Axis })}
                          className="col-span-2 px-2 py-1 border border-border-subtle rounded text-xs bg-bg">
                    <option value="left">Слева</option>
                    <option value="right">Справа</option>
                  </select>
                  <select value={m.chartType ?? chartType}
                          onChange={(e) => updateMetric(m.key, { chartType: e.target.value as ChartType })}
                          className="col-span-2 px-2 py-1 border border-border-subtle rounded text-xs bg-bg">
                    <option value="line">Линия</option>
                    <option value="bar">Столбцы</option>
                  </select>
                  <input type="color" value={m.color}
                         onChange={(e) => updateMetric(m.key, { color: e.target.value })}
                         className="col-span-2 w-full h-7 rounded border border-border-subtle cursor-pointer" />
                  <button onClick={() => setMetricsList(metricsList.filter(x => x.key !== m.key))}
                          className="col-span-1 text-fg-muted hover:text-rose-600">
                    <X className="size-3.5" />
                  </button>
                </div>
              )
            })}
          </div>
        )}

        {/* Каталог метрик */}
        <div className="relative mb-2">
          <Search className="size-4 absolute left-2 top-2 text-fg-muted" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
                 placeholder="поиск метрики…"
                 className="w-full pl-8 pr-3 py-1.5 border border-border-subtle rounded text-sm bg-bg" />
        </div>
        <div className="max-h-72 overflow-y-auto border border-border-subtle rounded p-2">
          {Object.entries(grouped).map(([group, items]) => (
            <div key={group} className="mb-2">
              <div className="text-[10px] uppercase text-fg-muted mb-0.5">{group}</div>
              {items.map(m => (
                <label key={m.key}
                       className={cn(
                         'flex items-center gap-2 py-0.5 px-1 rounded text-xs cursor-pointer',
                         isSelected(m.key) ? 'bg-accent/10' : 'hover:bg-bg-subtle/30',
                         !isSelected(m.key) && metricsList.length >= 4 && 'opacity-40 cursor-not-allowed',
                       )}
                       title={m.description}>
                  <input type="checkbox" checked={isSelected(m.key)}
                         onChange={() => toggleMetric(m)}
                         disabled={!isSelected(m.key) && metricsList.length >= 4} />
                  <span className="flex-1">{m.label}</span>
                  {m.source === 'model' && <span className="text-[9px] text-amber-700">оценка</span>}
                </label>
              ))}
            </div>
          ))}
        </div>

        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose}
                  className="px-4 py-2 text-sm border border-border-subtle rounded-lg hover:bg-bg-subtle/30">
            Отмена
          </button>
          <button onClick={() => onSave({ title, chartType, metrics: metricsList })}
                  className="inline-flex items-center gap-1 px-4 py-2 bg-accent text-white rounded-lg text-sm font-medium hover:bg-accent-hover">
            <Save className="size-4" /> Сохранить
          </button>
        </div>
      </div>
    </div>
  )
}
