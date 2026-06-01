import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Flag, Plus, Trash2, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { DateRangeBar } from '@/components/DateRangeBar'

interface MarkerRow {
  id: string
  marker_type: string
  title: string
  note: string | null
  product_id: string | null
  product_name: string | null
  offer_id: string | null
  created_at: string
}

interface ProductLite {
  id: string
  name: string
  offer_id: string
}

const TYPE_LABELS: Record<string, string> = {
  manual_note: 'Заметка',
  price_change: 'Изменение цены',
  content_update: 'Обновление контента',
  photo_update: 'Обновление фото',
  promo_start: 'Старт промо',
  promo_end: 'Конец промо',
  ad_campaign_start: 'Старт рекламы',
  procurement: 'Закупка',
  auto_stock_low: '⚠ Низкий сток',
  auto_stock_out: '🔴 Стокаут',
  auto_price_index_changed: 'Изменился индекс цен',
  auto_competitor_price_changed: 'Конкурент изменил цену',
  auto_position_dropped: '⬇ Позиция упала',
  auto_review_received: 'Новый отзыв',
  auto_anomaly_detected: '⚡ Аномалия',
}

const TYPE_COLORS: Record<string, string> = {
  manual_note: 'bg-indigo-50 text-indigo-700',
  price_change: 'bg-amber-50 text-amber-700',
  content_update: 'bg-violet-50 text-violet-700',
  photo_update: 'bg-violet-50 text-violet-700',
  promo_start: 'bg-emerald-50 text-emerald-700',
  promo_end: 'bg-rose-50 text-rose-700',
  ad_campaign_start: 'bg-blue-50 text-blue-700',
  procurement: 'bg-emerald-50 text-emerald-700',
  auto_stock_low: 'bg-amber-50 text-amber-700',
  auto_stock_out: 'bg-rose-50 text-rose-700',
  auto_anomaly_detected: 'bg-violet-50 text-violet-700',
}

export function Markers() {
  const qc = useQueryClient()
  const [days, setDays] = useState(90)
  const [showForm, setShowForm] = useState(false)

  const { data, isLoading } = useQuery<MarkerRow[]>({
    queryKey: ['markers', days],
    queryFn: async () => (await api.get(`/markers/?days=${days}`)).data,
  })

  const { data: products } = useQuery<ProductLite[]>({
    queryKey: ['products', 'lite'],
    queryFn: async () => {
      const all = (await api.get('/products/')).data as Array<{ id: string; name: string; offer_id: string }>
      return all.map((p) => ({ id: p.id, name: p.name, offer_id: p.offer_id }))
    },
  })

  const [markerType, setMarkerType] = useState('manual_note')
  const [title, setTitle] = useState('')
  const [note, setNote] = useState('')
  const [productId, setProductId] = useState('')

  const create = useMutation({
    mutationFn: async () => (await api.post('/markers/', {
      marker_type: markerType, title, note: note || null, product_id: productId || null,
    })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['markers'] })
      setShowForm(false)
      setTitle(''); setNote(''); setProductId('')
    },
  })

  const del = useMutation({
    mutationFn: async (id: string) => api.delete(`/markers/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['markers'] }),
  })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Маркеры событий</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            {data?.length ?? 0} событий · ручные пометки + автоматические (стокауты, изменения цен)
          </p>
        </div>
        <div className="flex gap-2">
          <DateRangeBar days={days} onChange={setDays} />
          <Button onClick={() => setShowForm((v) => !v)}>
            <Plus className="w-4 h-4" /> Маркер
          </Button>
        </div>
      </div>

      {showForm && (
        <Card className="p-5">
          <h3 className="text-base font-semibold text-fg mb-4">Новый маркер</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Тип</label>
              <select value={markerType} onChange={(e) => setMarkerType(e.target.value)}
                className="h-9 px-3 rounded-md border border-border bg-surface text-sm w-full">
                {Object.entries(TYPE_LABELS)
                  .filter(([k]) => !k.startsWith('auto_'))
                  .map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div className="md:col-span-2">
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Товар (опц)</label>
              <select value={productId} onChange={(e) => setProductId(e.target.value)}
                className="h-9 px-3 rounded-md border border-border bg-surface text-sm w-full">
                <option value="">— общий маркер —</option>
                {(products || []).map((p) => (
                  <option key={p.id} value={p.id}>{p.offer_id} · {p.name.slice(0, 40)}</option>
                ))}
              </select>
            </div>
            <div className="md:col-span-3">
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Заголовок</label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="напр. Снизил цену на 5%" />
            </div>
            <div className="md:col-span-3">
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Заметка (опц)</label>
              <textarea value={note} onChange={(e) => setNote(e.target.value)}
                className="min-h-[60px] w-full px-3 py-2 rounded-md border border-border bg-surface text-sm"
                placeholder="Дополнительный контекст" />
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="ghost" onClick={() => setShowForm(false)}>Отмена</Button>
            <Button onClick={() => create.mutate()} disabled={create.isPending || !title}>
              {create.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Сохранить'}
            </Button>
          </div>
        </Card>
      )}

      {isLoading ? (
        <Card className="py-16 flex justify-center"><Loader2 className="w-5 h-5 animate-spin" /></Card>
      ) : (data?.length ?? 0) === 0 ? (
        <Card className="py-12 flex flex-col items-center text-fg-muted text-sm">
          <Flag className="w-8 h-8 mb-2 text-fg-subtle" />
          <p>Маркеров пока нет. Добавьте первый — отметьте действие (промо, изменение цены, закупку).</p>
        </Card>
      ) : (
        <div className="flex flex-col gap-2">
          {data!.map((m) => (
            <Card key={m.id} className="p-3 flex items-start gap-3">
              <Flag className="w-4 h-4 text-fg-subtle mt-1 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={cn('text-[11px] font-medium px-1.5 py-0.5 rounded',
                    TYPE_COLORS[m.marker_type] || 'bg-fg-subtle/10 text-fg-muted')}>
                    {TYPE_LABELS[m.marker_type] || m.marker_type}
                  </span>
                  <span className="text-sm font-medium text-fg">{m.title}</span>
                  <span className="text-xs text-fg-subtle ml-auto">
                    {new Date(m.created_at).toLocaleString('ru-RU')}
                  </span>
                </div>
                {m.product_name && (
                  <div className="text-xs text-fg-muted mt-0.5 font-mono">{m.offer_id} · {m.product_name}</div>
                )}
                {m.note && <p className="text-sm text-fg-muted mt-1.5">{m.note}</p>}
              </div>
              <button onClick={() => del.mutate(m.id)} className="p-1 text-fg-subtle hover:text-rose-700">
                <Trash2 className="w-4 h-4" />
              </button>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
