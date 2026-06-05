import { useState, useEffect, useMemo } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, Calendar, Trash2, Paperclip, FileText, Upload, X, Save, Truck,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, cn } from '@/lib/utils'
import { TRANSPORT_META } from '@/pages/Supplies'

type SupplyStatus = 'ordered' | 'in_transit' | 'arrived'
type TransportType = 'rzd' | 'auto' | 'auto_consolidated' | 'cargo' | 'sea'

interface ProductLookup {
  id: string; offer_id: string; ozon_sku: number; name: string; cabinet_name: string
}
interface SupplyItem {
  id?: string; product_id: string | null; offer_id: string | null
  product_name?: string | null; name: string | null
  qty: number; final_unit_cost: number | null; note: string | null
}
interface SupplyCost {
  id?: string; name: string; amount: number
  currency: 'USD' | 'RUB' | null
  scope: 'supply' | 'item'
  supply_item_index?: number | null; supply_item_id?: string | null; note: string | null
}
interface SupplyDoc {
  id: string; filename: string; mime: string | null; size: number | null
  supply_item_id: string | null; uploaded_at: string
}
interface SupplyDetail {
  id: string; name: string; tag: string | null
  transport_type: TransportType | null; route: string | null
  notes: string | null
  cabinet_id: string | null; cabinet_name: string | null
  total_cost: number | null
  status: SupplyStatus
  payment_date: string | null; dispatch_date: string | null; dispatch_from: string | null
  actual_departure_date: string | null; supply_date: string | null
  items: (SupplyItem & { id: string })[]
  costs: (SupplyCost & { id: string })[]
  documents: SupplyDoc[]; total_costs_sum: number; created_at: string
}

export function SupplyDetailPage() {
  const { id: paramId } = useParams<{ id: string }>()
  const isNew = paramId === 'new'
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: products } = useQuery<ProductLookup[]>({
    queryKey: ['supplies-product-lookup'],
    queryFn: async () => (await api.get('/supplies/lookup/products')).data,
  })
  const { data: existing } = useQuery<SupplyDetail | undefined>({
    queryKey: ['supplies', paramId],
    queryFn: async () => isNew ? undefined : (await api.get(`/supplies/${paramId}`)).data,
    enabled: !isNew && !!paramId,
  })

  const [form, setForm] = useState({
    name: '', tag: '', transport_type: '' as TransportType | '', route: '',
    notes: '', status: 'arrived' as SupplyStatus,
    payment_date: '', dispatch_date: '', dispatch_from: '',
    actual_departure_date: '',
    supply_date: isNew ? new Date().toISOString().slice(0, 10) : '',
    total_cost: '',
    cabinet_id: '' as string | '',
  })
  // Кабинеты для селектора (отдельный запрос — store держит только выбранные id)
  const { data: cabinets = [] } = useQuery<{ id: string; name: string }[]>({
    queryKey: ['cabinets-for-supplies'],
    queryFn: async () => (await api.get('/ozon-accounts/')).data || [],
    staleTime: 5 * 60_000,
  })
  const [items, setItems] = useState<SupplyItem[]>([])
  const [costs, setCosts] = useState<SupplyCost[]>([])
  const [pendingFiles, setPendingFiles] = useState<{ file: File; scope: 'supply' | 'item'; itemIdx: number | null }[]>([])
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [loadedId, setLoadedId] = useState<string | null>(null)

  useEffect(() => {
    if (!existing || existing.id === loadedId) return
    setLoadedId(existing.id)
    setForm({
      name: existing.name, tag: existing.tag || '',
      transport_type: existing.transport_type || '',
      route: existing.route || '',
      notes: existing.notes || '', status: existing.status,
      payment_date: existing.payment_date || '',
      dispatch_date: existing.dispatch_date || '',
      dispatch_from: existing.dispatch_from || '',
      actual_departure_date: existing.actual_departure_date || '',
      supply_date: existing.supply_date || '',
      total_cost: existing.total_cost?.toString() || '',
      cabinet_id: existing.cabinet_id || '',
    })
    setItems(existing.items.map(i => ({
      id: i.id, product_id: i.product_id, offer_id: i.offer_id,
      product_name: i.product_name, name: i.name,
      qty: i.qty, final_unit_cost: i.final_unit_cost, note: i.note,
    })))
    setCosts(existing.costs.map(c => ({
      id: c.id, name: c.name, amount: c.amount,
      currency: c.currency, scope: c.scope, note: c.note,
      supply_item_index: c.supply_item_id
        ? existing.items.findIndex(i => i.id === c.supply_item_id)
        : null,
    })))
  }, [existing, loadedId])

  const sumByItem = (idx: number) => costs.filter(c => c.scope === 'item' && c.supply_item_index === idx)
    .reduce((s, c) => s + (Number(c.amount) || 0), 0)
  const sumSupply = costs.filter(c => c.scope === 'supply').reduce((s, c) => s + (Number(c.amount) || 0), 0)
  const totalCostsSum = costs.reduce((s, c) => s + (Number(c.amount) || 0), 0)
  // Итоги
  const itemsTotal = items.reduce((s, i) => s + (Number(i.final_unit_cost) || 0) * (Number(i.qty) || 0), 0)
  const grandTotal = itemsTotal + totalCostsSum
  const totalCostOverride = form.total_cost ? parseFloat(form.total_cost) : null

  const save = async () => {
    setError(null); setSaving(true)
    try {
      const payload = {
        name: form.name,
        tag: form.tag || null,
        transport_type: form.transport_type || null,
        route: form.route || null,
        notes: form.notes || null,
        status: form.status,
        total_cost: form.total_cost ? parseFloat(form.total_cost) : null,
        payment_date: form.payment_date || null,
        dispatch_date: form.dispatch_date || null,
        dispatch_from: form.dispatch_from || null,
        actual_departure_date: form.actual_departure_date || null,
        supply_date: form.supply_date || null,
        cabinet_id: form.cabinet_id || null,
        items: items.map(i => ({
          product_id: i.product_id, offer_id: i.offer_id,
          name: i.name, qty: i.qty,
          final_unit_cost: i.final_unit_cost, note: i.note,
        })),
        costs: costs.map(c => ({
          name: c.name, amount: Number(c.amount),
          currency: c.currency, scope: c.scope,
          supply_item_index: c.scope === 'item' ? c.supply_item_index : null,
          note: c.note,
        })),
      }
      const r = isNew
        ? await api.post('/supplies', payload)
        : await api.patch(`/supplies/${paramId}`, payload)
      const supplyId = r.data.id

      // Загружаем файлы по одному. Если какой-то упадёт — другие сохраняем,
      // оставляем упавшие в pendingFiles чтобы юзер мог повторить save.
      const failed: typeof pendingFiles = []
      const uploaded: typeof pendingFiles = []
      for (const pf of pendingFiles) {
        try {
          const fd = new FormData()
          fd.append('file', pf.file)
          if (pf.scope === 'item' && pf.itemIdx !== null && r.data.items[pf.itemIdx]) {
            fd.append('supply_item_id', r.data.items[pf.itemIdx].id)
          }
          await api.post(`/supplies/${supplyId}/documents`, fd, {
            headers: { 'Content-Type': 'multipart/form-data' },
          })
          uploaded.push(pf)
        } catch (upErr: any) {
          failed.push(pf)
          console.error('Не удалось загрузить файл:', pf.file.name, upErr)
        }
      }

      qc.invalidateQueries({ queryKey: ['supplies'] })
      if (isNew) {
        if (failed.length > 0) {
          // Сохраняем pending для повторной попытки на детальной странице
          setPendingFiles(failed)
          setError(`Поставка создана, но ${failed.length} файл(а) не загрузились. Нажми «Сохранить» ещё раз.`)
        }
        navigate(`/procurement/supplies/${supplyId}`, { replace: true })
      } else {
        qc.invalidateQueries({ queryKey: ['supplies', paramId] })
        setPendingFiles(failed)
        if (failed.length > 0) {
          setError(`Сохранено, но ${failed.length} файл(а) не загрузились (${uploaded.length} OK). Жми «Сохранить» снова.`)
        }
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Ошибка сохранения. Данные и файлы НЕ потеряны — попробуй ещё раз.')
    } finally {
      setSaving(false)
    }
  }

  // Защита от потери данных: warning перед уходом со страницы
  // если есть pending files или незавершённое редактирование
  useEffect(() => {
    if (pendingFiles.length === 0) return
    const beforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => window.removeEventListener('beforeunload', beforeUnload)
  }, [pendingFiles.length])

  return (
    <div className="flex flex-col gap-5 max-w-5xl">
      <div className="flex items-center justify-between gap-3">
        <button onClick={() => navigate('/procurement/supplies')}
                className="inline-flex items-center gap-2 text-sm text-fg-muted hover:text-fg">
          <ArrowLeft className="size-4" /> К списку поставок
        </button>
        <div className="flex gap-2">
          <button onClick={save}
                  disabled={!form.name || saving}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-accent text-white rounded-lg text-sm font-medium hover:bg-accent-hover disabled:opacity-50">
            <Save className="size-4" /> {saving ? 'Сохраняю…' : (isNew ? 'Создать' : 'Сохранить')}
          </button>
        </div>
      </div>

      <div>
        <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
          <Truck className="size-5 text-fg-muted" />
          {isNew ? 'Новая поставка' : (form.name || '—')}
        </h1>
      </div>

      {error && (
        <div className="px-4 py-3 bg-rose-50 border border-rose-200 rounded text-sm text-rose-800">
          {error}
        </div>
      )}

      {/* Шапка: название + тэг + статус */}
      <Card className="p-4">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
          <Field className="md:col-span-5" label="Название*" value={form.name}
                 onChange={(v) => setForm({ ...form, name: v })}
                 placeholder="например: Жираф февраль 2026" />
          <Field className="md:col-span-3" label="Метка / тэг" value={form.tag}
                 onChange={(v) => setForm({ ...form, tag: v })}
                 placeholder="партия, поставщик…" />
          <div className="md:col-span-2">
            <label className="text-[10px] text-fg-muted uppercase block mb-1">Статус</label>
            <select value={form.status}
                    onChange={(e) => setForm({ ...form, status: e.target.value as SupplyStatus })}
                    className="w-full px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg">
              <option value="ordered">Заказана</option>
              <option value="in_transit">В пути</option>
              <option value="arrived">Получена</option>
            </select>
          </div>
          <Field className="md:col-span-2" label="Итог. стоимость ₽" type="number" value={form.total_cost}
                 onChange={(v) => setForm({ ...form, total_cost: v })} placeholder="справочно" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3 mt-3">
          <div className="md:col-span-4">
            <label className="text-[10px] text-fg-muted uppercase block mb-1">Кабинет Ozon</label>
            <select value={form.cabinet_id}
                    onChange={(e) => setForm({ ...form, cabinet_id: e.target.value })}
                    className="w-full px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg">
              <option value="">— не указан —</option>
              {cabinets.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          <div className="md:col-span-3">
            <label className="text-[10px] text-fg-muted uppercase block mb-1">Тип перевозки</label>
            <select value={form.transport_type}
                    onChange={(e) => setForm({ ...form, transport_type: e.target.value as TransportType | '' })}
                    className="w-full px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg">
              <option value="">—</option>
              {(Object.entries(TRANSPORT_META) as [TransportType, string][]).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
          <Field className="md:col-span-5" label="Маршрут" value={form.route}
                 onChange={(v) => setForm({ ...form, route: v })}
                 placeholder="например: Шэньчжэнь → Алматы → Москва" />
        </div>
      </Card>

      {/* Даты */}
      <Card className="p-4">
        <div className="text-xs font-medium text-fg-muted uppercase mb-2 flex items-center gap-1">
          <Calendar className="size-3" /> Даты
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          <Field label="Оплата" type="date" value={form.payment_date}
                 onChange={(v) => setForm({ ...form, payment_date: v })} />
          <Field label="Отправка" type="date" value={form.dispatch_date}
                 onChange={(v) => setForm({ ...form, dispatch_date: v })} />
          <Field label="Откуда" value={form.dispatch_from}
                 onChange={(v) => setForm({ ...form, dispatch_from: v })}
                 placeholder="станция / склад" />
          <Field label="Факт. выход" type="date" value={form.actual_departure_date}
                 onChange={(v) => setForm({ ...form, actual_departure_date: v })} />
          <Field label="Приход" type="date" value={form.supply_date}
                 onChange={(v) => setForm({ ...form, supply_date: v })} />
        </div>
      </Card>

      {/* Позиции */}
      <Card className="p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-fg">Позиции (SKU)</h2>
          <button onClick={() => setItems([...items, { product_id: null, offer_id: null, name: null, qty: 1, final_unit_cost: null, note: null }])}
                  className="text-xs text-accent hover:underline">+ позиция</button>
        </div>
        {items.length === 0 && <div className="text-xs text-fg-muted py-2">Добавь товары из каталога</div>}
        {items.map((it, idx) => {
          const isNewItem = !it.product_id  // SKU не выбран → товар «новый», вне каталога
          return (
            <div key={idx} className="border border-fg-subtle/15 rounded-md p-3 mb-2 space-y-2">
              <div className="grid grid-cols-12 gap-2 items-start">
                <div className="col-span-5">
                  <label className="text-[10px] text-fg-muted uppercase block mb-1">SKU из каталога</label>
                  <select value={it.product_id || ''}
                          onChange={(e) => {
                            const p = products?.find(x => x.id === e.target.value)
                            setItems(items.map((i, i2) => i2 === idx ? {
                              ...i, product_id: p?.id || null, offer_id: p?.offer_id || null,
                              product_name: p?.name,
                            } : i))
                          }}
                          className="w-full px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg">
                    <option value="">— новый товар (не из каталога) —</option>
                    {products?.map(p => (
                      <option key={p.id} value={p.id}>
                        {p.offer_id} — {p.name.slice(0, 40)} ({p.cabinet_name})
                      </option>
                    ))}
                  </select>
                </div>
                <input type="number" value={it.qty}
                       onChange={(e) => setItems(items.map((i, i2) => i2 === idx ? { ...i, qty: parseInt(e.target.value) || 0 } : i))}
                       placeholder="шт" className="col-span-1 px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg self-end" />
                <input type="number" value={it.final_unit_cost ?? ''}
                       onChange={(e) => setItems(items.map((i, i2) => i2 === idx ? { ...i, final_unit_cost: e.target.value ? parseFloat(e.target.value) : null } : i))}
                       placeholder="себес/ед ₽" className="col-span-2 px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg self-end" />
                <input value={it.note ?? ''}
                       onChange={(e) => setItems(items.map((i, i2) => i2 === idx ? { ...i, note: e.target.value || null } : i))}
                       placeholder="заметка" className="col-span-3 px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg self-end" />
                <button onClick={() => setItems(items.filter((_, i2) => i2 !== idx))}
                        className="col-span-1 text-fg-muted hover:text-rose-600 py-1.5 self-end">
                  <Trash2 className="size-4" />
                </button>
              </div>
              {isNewItem && (
                <input value={it.name ?? ''}
                       onChange={(e) => setItems(items.map((i, i2) => i2 === idx ? { ...i, name: e.target.value || null } : i))}
                       placeholder="Название нового товара (обязательно для не-каталожных)"
                       className="w-full px-2 py-1.5 border border-amber-300 rounded text-sm bg-amber-50/30" />
              )}
              {sumByItem(idx) > 0 && (
                <div className="text-[10px] text-fg-muted">
                  Σ затрат на этот товар: <b>{formatCurrency(sumByItem(idx))}</b> (справочно)
                </div>
              )}
            </div>
          )
        })}
      </Card>

      {/* Затраты */}
      <Card className="p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-fg">Затраты</h2>
          <button onClick={() => setCosts([...costs, { name: '', amount: 0, currency: null, scope: 'supply', note: null }])}
                  className="text-xs text-accent hover:underline">+ затрата</button>
        </div>
        {costs.length === 0 && <div className="text-xs text-fg-muted py-2">Доставка, растаможка, документы, сертификаты…</div>}
        {costs.map((c, idx) => (
          <div key={idx} className="grid grid-cols-12 gap-2 mb-2">
            <input value={c.name}
                   onChange={(e) => setCosts(costs.map((cc, i2) => i2 === idx ? { ...cc, name: e.target.value } : cc))}
                   placeholder="доставка" className="col-span-3 px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg" />
            <input type="number" value={c.amount}
                   onChange={(e) => setCosts(costs.map((cc, i2) => i2 === idx ? { ...cc, amount: parseFloat(e.target.value) || 0 } : cc))}
                   placeholder="сумма" className="col-span-2 px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg" />
            <select value={c.currency || ''}
                    onChange={(e) => setCosts(costs.map((cc, i2) => i2 === idx ? { ...cc, currency: (e.target.value || null) as any } : cc))}
                    className="col-span-1 px-1 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg">
              <option value="">—</option>
              <option value="RUB">₽</option>
              <option value="USD">$</option>
            </select>
            <select value={c.scope}
                    onChange={(e) => setCosts(costs.map((cc, i2) => i2 === idx ? { ...cc, scope: e.target.value as any, supply_item_index: null } : cc))}
                    className="col-span-2 px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg">
              <option value="supply">на поставку</option>
              <option value="item">на товар</option>
            </select>
            {c.scope === 'item' ? (
              <select value={c.supply_item_index ?? ''}
                      onChange={(e) => setCosts(costs.map((cc, i2) => i2 === idx ? { ...cc, supply_item_index: e.target.value === '' ? null : parseInt(e.target.value) } : cc))}
                      className="col-span-2 px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg">
                <option value="">— SKU —</option>
                {items.map((i, i2) => (
                  <option key={i2} value={i2}>
                    {i.product_id ? (i.offer_id || `#${i2 + 1}`) : (i.name || `новый #${i2 + 1}`)}
                  </option>
                ))}
              </select>
            ) : <div className="col-span-2" />}
            <input value={c.note ?? ''}
                   onChange={(e) => setCosts(costs.map((cc, i2) => i2 === idx ? { ...cc, note: e.target.value || null } : cc))}
                   placeholder="заметка" className="col-span-1 px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg" />
            <button onClick={() => setCosts(costs.filter((_, i2) => i2 !== idx))}
                    className="col-span-1 text-fg-muted hover:text-rose-600 py-1.5">
              <Trash2 className="size-4" />
            </button>
          </div>
        ))}
        {totalCostsSum > 0 && (
          <div className="mt-3 px-3 py-2 bg-bg-subtle/40 rounded text-xs">
            <div>Σ затрат всего: <b>{formatCurrency(totalCostsSum)}</b> · из них на всю поставку: <b>{formatCurrency(sumSupply)}</b></div>
            <div className="text-fg-muted mt-1">Суммы затрат НЕ записываются в себестоимость автоматически. Используй для ручного пересчёта final_unit_cost.</div>
          </div>
        )}
      </Card>

      {/* Итоги */}
      <Card className="p-4 border-2 border-indigo-200 bg-indigo-50/30">
        <h2 className="text-sm font-medium text-fg mb-3">Итоги</h2>
        <div className="space-y-1.5 text-sm">
          <div className="flex justify-between">
            <span className="text-fg-muted">Все за товар (Σ final_unit_cost × qty)</span>
            <span className="tabular-nums font-medium">{formatCurrency(itemsTotal)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-fg-muted">Все за доставку и затраты (Σ amount)</span>
            <span className="tabular-nums font-medium">{formatCurrency(totalCostsSum)}</span>
          </div>
          <div className="flex justify-between pt-2 mt-1 border-t border-indigo-200 text-base">
            <span className="font-semibold">ИТОГО (товар + затраты)</span>
            <span className="tabular-nums font-bold text-indigo-900">{formatCurrency(grandTotal)}</span>
          </div>
          {totalCostOverride !== null && Math.abs(totalCostOverride - grandTotal) > 1 && (
            <div className="flex justify-between text-xs text-amber-700 mt-1">
              <span>⚠ Расхождение с введённым «Итог. стоимость» ({formatCurrency(totalCostOverride)})</span>
              <span>Δ = {formatCurrency(totalCostOverride - grandTotal)}</span>
            </div>
          )}
        </div>
      </Card>

      {/* Документы */}
      <Card className="p-4">
        <div className="text-sm font-medium text-fg mb-3 flex items-center gap-1">
          <Paperclip className="size-4 text-fg-muted" /> Документы
        </div>
        {existing && existing.documents.length > 0 && (
          <div className="mb-3 space-y-1">
            {existing.documents.map(d => (
              <DocItem key={d.id} doc={d} supplyId={existing.id}
                       onDelete={async () => {
                         await api.delete(`/supplies/${existing.id}/documents/${d.id}`)
                         qc.invalidateQueries({ queryKey: ['supplies', existing.id] })
                       }} />
            ))}
          </div>
        )}
        <DropZone
          items={items}
          onFiles={(files, scope, itemIdx) => setPendingFiles([
            ...pendingFiles,
            ...files.map(f => ({ file: f, scope, itemIdx })),
          ])}
        />
        {pendingFiles.length > 0 && (
          <div className="mt-3 space-y-1">
            {pendingFiles.map((pf, idx) => (
              <div key={idx} className="flex items-center justify-between px-3 py-1.5 bg-amber-50 border border-amber-200 rounded text-xs">
                <span className="flex items-center gap-1">
                  <FileText className="size-3" /> {pf.file.name}
                  <span className="ml-2 text-fg-muted">
                    {pf.scope === 'supply' ? 'общий' : `к товару #${(pf.itemIdx ?? 0) + 1}`}
                  </span>
                </span>
                <button onClick={() => setPendingFiles(pendingFiles.filter((_, i2) => i2 !== idx))}>
                  <X className="size-3" />
                </button>
              </div>
            ))}
            <div className="text-[10px] text-fg-muted">Загрузятся при сохранении</div>
          </div>
        )}
      </Card>

      {/* Заметки */}
      <Card className="p-4">
        <label className="text-sm font-medium text-fg block mb-2">Общие заметки</label>
        <textarea value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  placeholder="что-то особенное по этой поставке…"
                  rows={3}
                  className="w-full px-3 py-2 border border-fg-subtle/30 rounded text-sm bg-bg" />
      </Card>

      {/* Финальная кнопка */}
      <div className="flex justify-end">
        <button onClick={save}
                disabled={!form.name || saving}
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-accent text-white rounded-lg text-sm font-medium hover:bg-accent-hover disabled:opacity-50">
          <Save className="size-4" /> {saving ? 'Сохраняю…' : (isNew ? 'Создать поставку' : 'Сохранить изменения')}
        </button>
      </div>
    </div>
  )
}

// ===== sub-components =====

function DocItem({ doc, supplyId, onDelete }: {
  doc: SupplyDoc; supplyId: string; onDelete: () => void
}) {
  const open = async () => {
    const r = await api.get(`/supplies/${supplyId}/documents/${doc.id}/url`)
    window.open(r.data.url, '_blank')
  }
  return (
    <div className="flex items-center justify-between px-3 py-1.5 bg-bg-subtle/30 rounded text-sm">
      <span className="flex items-center gap-2">
        <FileText className="size-4 text-fg-muted" />
        <button onClick={open} className="text-accent hover:underline">{doc.filename}</button>
        {doc.size && <span className="text-fg-muted text-xs">({(doc.size / 1024).toFixed(0)} КБ)</span>}
      </span>
      <button onClick={() => { if (confirm(`Удалить ${doc.filename}?`)) onDelete() }}
              className="text-fg-muted hover:text-rose-600">
        <Trash2 className="size-3" />
      </button>
    </div>
  )
}

function DropZone({ items, onFiles }: {
  items: SupplyItem[]
  onFiles: (files: File[], scope: 'supply' | 'item', itemIdx: number | null) => void
}) {
  const [drag, setDrag] = useState(false)
  const [scope, setScope] = useState<'supply' | 'item'>('supply')
  const [itemIdx, setItemIdx] = useState<number | null>(null)

  return (
    <div className="space-y-2">
      <div className="flex gap-3 items-center text-xs">
        <span className="text-fg-muted">Привязать:</span>
        <label className="flex items-center gap-1">
          <input type="radio" checked={scope === 'supply'} onChange={() => setScope('supply')} />
          к поставке
        </label>
        <label className="flex items-center gap-1">
          <input type="radio" checked={scope === 'item'} onChange={() => setScope('item')} disabled={items.length === 0} />
          к товару
        </label>
        {scope === 'item' && items.length > 0 && (
          <select value={itemIdx ?? ''} onChange={(e) => setItemIdx(parseInt(e.target.value))}
                  className="px-2 py-1 border border-fg-subtle/30 rounded text-xs bg-bg">
            <option value="">—</option>
            {items.map((i, idx) => <option key={idx} value={idx}>{i.offer_id || `#${idx + 1}`}</option>)}
          </select>
        )}
      </div>
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault(); setDrag(false)
          const files = Array.from(e.dataTransfer.files)
          if (files.length) onFiles(files, scope, scope === 'item' ? itemIdx : null)
        }}
        className={cn(
          'border-2 border-dashed rounded-md p-5 text-center text-sm cursor-pointer',
          drag ? 'border-accent bg-accent/5' : 'border-fg-subtle/30 hover:bg-bg-subtle/30',
        )}
        onClick={() => document.getElementById('supply-detail-file-input')?.click()}
      >
        <Upload className="size-5 mx-auto mb-1 text-fg-muted" />
        Перетащи файлы сюда или нажми (pdf, jpg, png, xlsx, docx; до 25 МБ)
        <input id="supply-detail-file-input" type="file" multiple hidden
               onChange={(e) => {
                 const files = Array.from(e.target.files || [])
                 if (files.length) onFiles(files, scope, scope === 'item' ? itemIdx : null)
               }} />
      </div>
    </div>
  )
}

function Field({ label, value, onChange, placeholder, type = 'text', className = '' }: {
  label: string; value: string; onChange: (v: string) => void
  placeholder?: string; type?: string; className?: string
}) {
  return (
    <div className={className}>
      <label className="text-[10px] text-fg-muted uppercase block mb-1">{label}</label>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)}
             placeholder={placeholder}
             className="w-full px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg" />
    </div>
  )
}
