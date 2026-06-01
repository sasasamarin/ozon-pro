import { useState, useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Truck, Plus, Loader2, Calendar, Trash2, Paperclip, FileText,
  Upload, X, ChevronDown, ChevronUp, Download,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, cn } from '@/lib/utils'

// =========== types ===========

interface ProductLookup {
  id: string; offer_id: string; ozon_sku: number; name: string; cabinet_name: string
}
interface SupplyListRow {
  id: string; name: string; supply_date: string | null
  items_count: number; costs_sum: number; docs_count: number
}
interface SupplyItem {
  id?: string; product_id: string | null; offer_id: string | null
  product_name?: string | null; qty: number; final_unit_cost: number | null; note: string | null
}
interface SupplyCost {
  id?: string; name: string; amount: number; scope: 'supply' | 'item'
  supply_item_index?: number | null; supply_item_id?: string | null; note: string | null
}
interface SupplyDoc {
  id: string; filename: string; mime: string | null; size: number | null
  supply_item_id: string | null; uploaded_at: string
}
interface SupplyDetail {
  id: string; name: string; notes: string | null
  cabinet_id: string | null; cabinet_name: string | null
  total_cost: number | null
  payment_date: string | null; dispatch_date: string | null; dispatch_from: string | null
  actual_departure_date: string | null; supply_date: string | null
  items: (SupplyItem & { id: string })[]; costs: (SupplyCost & { id: string })[]
  documents: SupplyDoc[]; total_costs_sum: number; created_at: string
}

// =========== page ===========

export function Supplies() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  const { data: list, isLoading } = useQuery<SupplyListRow[]>({
    queryKey: ['supplies', 'list'],
    queryFn: async () => (await api.get('/supplies')).data,
  })

  const del = useMutation({
    mutationFn: async (id: string) => api.delete(`/supplies/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['supplies'] }),
  })

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Поставки</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Ручной ввод поставок (машина/вагон) с SKU, затратами и документами.
            Себестоимость за единицу считаешь сам — авто-распределения нет.
          </p>
        </div>
        <button
          onClick={() => { setEditingId(null); setShowForm(true) }}
          className="inline-flex items-center gap-2 px-4 py-2 bg-accent text-white rounded-lg text-sm font-medium hover:bg-accent-hover"
        >
          <Plus className="size-4" /> Поставка
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="size-6 animate-spin text-fg-muted" />
        </div>
      ) : !list?.length ? (
        <Card className="p-12 text-center">
          <Truck className="size-12 mx-auto text-fg-muted/40" />
          <p className="text-fg-muted mt-3">Пока нет ни одной поставки</p>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase text-fg-muted bg-bg-subtle/40">
                <th className="px-4 py-2.5 w-8"></th>
                <th className="px-4 py-2.5">Дата</th>
                <th className="px-4 py-2.5">Метка</th>
                <th className="px-4 py-2.5 text-right">SKU</th>
                <th className="px-4 py-2.5 text-right">Σ затрат</th>
                <th className="px-4 py-2.5 text-center">📎</th>
                <th className="px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {list.map(s => (
                <>
                  <tr key={s.id} className="border-t border-fg-subtle/10 hover:bg-bg-subtle/30 cursor-pointer"
                      onClick={() => setExpanded(expanded === s.id ? null : s.id)}>
                    <td className="px-4 py-3">
                      {expanded === s.id
                        ? <ChevronUp className="size-4 text-fg-muted" />
                        : <ChevronDown className="size-4 text-fg-muted" />}
                    </td>
                    <td className="px-4 py-3 tabular-nums">{s.supply_date ?? '—'}</td>
                    <td className="px-4 py-3 font-medium">{s.name}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{s.items_count}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{formatCurrency(s.costs_sum)}</td>
                    <td className="px-4 py-3 text-center text-fg-muted">{s.docs_count || ''}</td>
                    <td className="px-4 py-3 text-right">
                      <button onClick={(e) => { e.stopPropagation(); setEditingId(s.id); setShowForm(true) }}
                              className="text-xs text-accent hover:underline mr-2">Редактировать</button>
                      <button onClick={(e) => { e.stopPropagation(); if (confirm(`Удалить «${s.name}»?`)) del.mutate(s.id) }}
                              className="text-fg-muted hover:text-rose-600">
                        <Trash2 className="size-4" />
                      </button>
                    </td>
                  </tr>
                  {expanded === s.id && (
                    <tr><td colSpan={7} className="bg-bg-subtle/20"><SupplyExpanded supplyId={s.id} /></td></tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {showForm && (
        <SupplyForm
          editingId={editingId}
          onClose={() => setShowForm(false)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ['supplies'] })
            setShowForm(false)
          }}
        />
      )}
    </div>
  )
}

// =========== expanded row (details + docs) ===========

function SupplyExpanded({ supplyId }: { supplyId: string }) {
  const { data } = useQuery<SupplyDetail>({
    queryKey: ['supplies', supplyId],
    queryFn: async () => (await api.get(`/supplies/${supplyId}`)).data,
  })
  if (!data) return <div className="p-4"><Loader2 className="size-4 animate-spin" /></div>
  return (
    <div className="p-4 space-y-3 text-sm">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
        {data.payment_date && <DateChip label="Оплата" v={data.payment_date} />}
        {data.dispatch_date && <DateChip label="Отправка" v={data.dispatch_date} />}
        {data.dispatch_from && <DateChip label="Откуда" v={data.dispatch_from} />}
        {data.actual_departure_date && <DateChip label="Факт. выход" v={data.actual_departure_date} />}
        {data.supply_date && <DateChip label="Приход" v={data.supply_date} />}
      </div>
      <div>
        <div className="text-xs font-medium text-fg-muted uppercase mb-1">Позиции</div>
        <table className="w-full text-xs">
          <tbody>
            {data.items.map(i => (
              <tr key={i.id} className="border-t border-fg-subtle/10">
                <td className="py-1 pr-3 font-mono">{i.offer_id}</td>
                <td className="py-1 pr-3 text-fg-muted">{i.product_name || '—'}</td>
                <td className="py-1 pr-3 text-right">{i.qty} шт</td>
                <td className="py-1 pr-3 text-right tabular-nums">
                  {i.final_unit_cost != null ? `${formatCurrency(i.final_unit_cost)}/ед` : '—'}
                </td>
                <td className="py-1 text-fg-muted text-xs">{i.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.costs.length > 0 && (
        <div>
          <div className="text-xs font-medium text-fg-muted uppercase mb-1">Затраты</div>
          {data.costs.map(c => (
            <div key={c.id} className="flex justify-between items-baseline py-0.5 text-xs">
              <span>
                {c.name}
                {c.scope === 'item' && (
                  <span className="ml-2 px-1.5 py-0.5 bg-amber-100 text-amber-800 rounded text-[10px]">на товар</span>
                )}
                {c.note && <span className="text-fg-muted ml-2">— {c.note}</span>}
              </span>
              <span className="tabular-nums font-medium">{formatCurrency(c.amount)}</span>
            </div>
          ))}
          <div className="flex justify-between mt-2 pt-2 border-t border-fg-subtle/15 font-medium">
            <span>Σ затрат (справочно)</span>
            <span className="tabular-nums">{formatCurrency(data.total_costs_sum)}</span>
          </div>
        </div>
      )}
      {data.documents.length > 0 && (
        <div>
          <div className="text-xs font-medium text-fg-muted uppercase mb-1">
            <Paperclip className="size-3 inline mr-1" />Документы
          </div>
          {data.documents.map(d => <DocChip key={d.id} doc={d} supplyId={supplyId} />)}
        </div>
      )}
      {data.notes && (
        <div className="bg-bg-subtle/40 rounded px-3 py-2 text-xs">
          <b>Заметки:</b> {data.notes}
        </div>
      )}
    </div>
  )
}

function DateChip({ label, v }: { label: string; v: string }) {
  return (
    <div className="px-2 py-1 bg-bg-subtle/40 rounded">
      <div className="text-[10px] text-fg-muted uppercase">{label}</div>
      <div className="font-medium">{v}</div>
    </div>
  )
}

function DocChip({ doc, supplyId }: { doc: SupplyDoc; supplyId: string }) {
  const open = async () => {
    const r = await api.get(`/supplies/${supplyId}/documents/${doc.id}/url`)
    window.open(r.data.url, '_blank')
  }
  return (
    <div className="flex items-center gap-2 py-1 text-xs">
      <FileText className="size-3 text-fg-muted" />
      <button onClick={open} className="text-accent hover:underline">{doc.filename}</button>
      {doc.size && <span className="text-fg-muted">({(doc.size / 1024).toFixed(0)} КБ)</span>}
    </div>
  )
}

// =========== form (create/edit) ===========

function SupplyForm({
  editingId, onClose, onSaved,
}: { editingId: string | null; onClose: () => void; onSaved: () => void }) {
  const qc = useQueryClient()
  const { data: products } = useQuery<ProductLookup[]>({
    queryKey: ['supplies-product-lookup'],
    queryFn: async () => (await api.get('/supplies/lookup/products')).data,
  })
  const { data: editing } = useQuery<SupplyDetail | undefined>({
    queryKey: ['supplies', editingId],
    queryFn: async () => editingId ? (await api.get(`/supplies/${editingId}`)).data : undefined,
    enabled: !!editingId,
  })

  const [form, setForm] = useState({
    name: '', notes: '',
    payment_date: '', dispatch_date: '', dispatch_from: '',
    actual_departure_date: '', supply_date: new Date().toISOString().slice(0, 10),
    total_cost: '',
  })
  const [items, setItems] = useState<SupplyItem[]>([])
  const [costs, setCosts] = useState<SupplyCost[]>([])
  // Локально новые документы (для редактируемой поставки) подгружаются после save
  const [pendingFiles, setPendingFiles] = useState<{ file: File; scope: 'supply' | 'item'; itemIdx: number | null }[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Заполняем форму из existing
  useMemo(() => {
    if (!editing) return
    setForm({
      name: editing.name, notes: editing.notes || '',
      payment_date: editing.payment_date || '',
      dispatch_date: editing.dispatch_date || '',
      dispatch_from: editing.dispatch_from || '',
      actual_departure_date: editing.actual_departure_date || '',
      supply_date: editing.supply_date || '',
      total_cost: editing.total_cost?.toString() || '',
    })
    setItems(editing.items.map(i => ({
      id: i.id, product_id: i.product_id, offer_id: i.offer_id,
      product_name: i.product_name, qty: i.qty,
      final_unit_cost: i.final_unit_cost, note: i.note,
    })))
    setCosts(editing.costs.map(c => ({
      id: c.id, name: c.name, amount: c.amount, scope: c.scope, note: c.note,
      supply_item_index: c.supply_item_id
        ? editing.items.findIndex(i => i.id === c.supply_item_id)
        : null,
    })))
  }, [editing])

  // Справочно: Σ по выбранному товару
  const sumByItem = (idx: number) =>
    costs.filter(c => c.scope === 'item' && c.supply_item_index === idx)
      .reduce((s, c) => s + (Number(c.amount) || 0), 0)
  const sumSupply = costs.filter(c => c.scope === 'supply')
    .reduce((s, c) => s + (Number(c.amount) || 0), 0)
  const totalCostsSum = costs.reduce((s, c) => s + (Number(c.amount) || 0), 0)

  const save = async () => {
    setError(null); setSaving(true)
    try {
      const payload = {
        name: form.name,
        notes: form.notes || null,
        total_cost: form.total_cost ? parseFloat(form.total_cost) : null,
        payment_date: form.payment_date || null,
        dispatch_date: form.dispatch_date || null,
        dispatch_from: form.dispatch_from || null,
        actual_departure_date: form.actual_departure_date || null,
        supply_date: form.supply_date || null,
        items: items.map(i => ({
          product_id: i.product_id, offer_id: i.offer_id,
          qty: i.qty, final_unit_cost: i.final_unit_cost, note: i.note,
        })),
        costs: costs.map(c => ({
          name: c.name, amount: Number(c.amount), scope: c.scope,
          supply_item_index: c.scope === 'item' ? c.supply_item_index : null,
          note: c.note,
        })),
      }
      const r = editingId
        ? await api.patch(`/supplies/${editingId}`, payload)
        : await api.post('/supplies', payload)
      const supplyId = r.data.id

      // Загружаем pending файлы (если есть)
      for (const pf of pendingFiles) {
        const fd = new FormData()
        fd.append('file', pf.file)
        if (pf.scope === 'item' && pf.itemIdx !== null && r.data.items[pf.itemIdx]) {
          fd.append('supply_item_id', r.data.items[pf.itemIdx].id)
        }
        await api.post(`/supplies/${supplyId}/documents`, fd, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
      }
      qc.invalidateQueries({ queryKey: ['supplies'] })
      onSaved()
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-start justify-center z-50 p-4 overflow-y-auto"
         onClick={onClose}>
      <div className="bg-bg rounded-xl shadow-xl max-w-4xl w-full p-6 my-8"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-4">
          <h2 className="text-xl font-semibold text-fg">
            {editingId ? 'Редактировать поставку' : 'Новая поставка'}
          </h2>
          <button onClick={onClose} className="text-fg-muted hover:text-fg"><X className="size-5" /></button>
        </div>

        {/* Шапка */}
        <div className="grid grid-cols-2 gap-3 mb-4">
          <Field label="Метка / название*" value={form.name}
                 onChange={(v) => setForm({ ...form, name: v })}
                 placeholder="Партия 2026-06, машина-1" />
          <Field label="Итоговая стоимость поставки, ₽ (опц.)" type="number" value={form.total_cost}
                 onChange={(v) => setForm({ ...form, total_cost: v })} placeholder="справочно" />
        </div>

        {/* Даты */}
        <div className="mb-4">
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
        </div>

        {/* Позиции */}
        <div className="mb-4">
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs font-medium text-fg-muted uppercase">Позиции (SKU)</div>
            <button onClick={() => setItems([...items, { product_id: null, offer_id: null, qty: 1, final_unit_cost: null, note: null }])}
                    className="text-xs text-accent hover:underline">+ позиция</button>
          </div>
          {items.length === 0 && <div className="text-xs text-fg-muted py-2">Добавь товары из каталога</div>}
          {items.map((it, idx) => (
            <div key={idx} className="grid grid-cols-12 gap-2 mb-2 items-start">
              <div className="col-span-5">
                <select value={it.product_id || ''}
                        onChange={(e) => {
                          const p = products?.find(x => x.id === e.target.value)
                          setItems(items.map((i, i2) => i2 === idx ? {
                            ...i, product_id: p?.id || null, offer_id: p?.offer_id || null,
                            product_name: p?.name,
                          } : i))
                        }}
                        className="w-full px-2 py-1.5 border border-fg-subtle/30 rounded text-xs bg-bg">
                  <option value="">— SKU —</option>
                  {products?.map(p => (
                    <option key={p.id} value={p.id}>
                      {p.offer_id} — {p.name.slice(0, 40)} ({p.cabinet_name})
                    </option>
                  ))}
                </select>
              </div>
              <input type="number" value={it.qty}
                     onChange={(e) => setItems(items.map((i, i2) => i2 === idx ? { ...i, qty: parseInt(e.target.value) || 0 } : i))}
                     placeholder="шт" className="col-span-2 px-2 py-1.5 border border-fg-subtle/30 rounded text-xs bg-bg" />
              <input type="number" value={it.final_unit_cost ?? ''}
                     onChange={(e) => setItems(items.map((i, i2) => i2 === idx ? { ...i, final_unit_cost: e.target.value ? parseFloat(e.target.value) : null } : i))}
                     placeholder="себес/ед ₽" className="col-span-2 px-2 py-1.5 border border-fg-subtle/30 rounded text-xs bg-bg" />
              <input value={it.note ?? ''}
                     onChange={(e) => setItems(items.map((i, i2) => i2 === idx ? { ...i, note: e.target.value || null } : i))}
                     placeholder="заметка" className="col-span-2 px-2 py-1.5 border border-fg-subtle/30 rounded text-xs bg-bg" />
              <button onClick={() => setItems(items.filter((_, i2) => i2 !== idx))}
                      className="col-span-1 text-fg-muted hover:text-rose-600">
                <Trash2 className="size-4" />
              </button>
              {sumByItem(idx) > 0 && (
                <div className="col-span-12 text-[10px] text-fg-muted pl-2">
                  Σ затрат на этот товар: <b>{formatCurrency(sumByItem(idx))}</b> (справочно)
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Затраты */}
        <div className="mb-4">
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs font-medium text-fg-muted uppercase">Затраты</div>
            <button onClick={() => setCosts([...costs, { name: '', amount: 0, scope: 'supply', note: null }])}
                    className="text-xs text-accent hover:underline">+ затрата</button>
          </div>
          {costs.length === 0 && <div className="text-xs text-fg-muted py-2">Доставка, растаможка, документы, сертификаты…</div>}
          {costs.map((c, idx) => (
            <div key={idx} className="grid grid-cols-12 gap-2 mb-2">
              <input value={c.name}
                     onChange={(e) => setCosts(costs.map((cc, i2) => i2 === idx ? { ...cc, name: e.target.value } : cc))}
                     placeholder="доставка" className="col-span-3 px-2 py-1.5 border border-fg-subtle/30 rounded text-xs bg-bg" />
              <input type="number" value={c.amount}
                     onChange={(e) => setCosts(costs.map((cc, i2) => i2 === idx ? { ...cc, amount: parseFloat(e.target.value) || 0 } : cc))}
                     placeholder="₽" className="col-span-2 px-2 py-1.5 border border-fg-subtle/30 rounded text-xs bg-bg" />
              <select value={c.scope}
                      onChange={(e) => setCosts(costs.map((cc, i2) => i2 === idx ? { ...cc, scope: e.target.value as any, supply_item_index: null } : cc))}
                      className="col-span-2 px-2 py-1.5 border border-fg-subtle/30 rounded text-xs bg-bg">
                <option value="supply">на поставку</option>
                <option value="item">на товар</option>
              </select>
              {c.scope === 'item' ? (
                <select value={c.supply_item_index ?? ''}
                        onChange={(e) => setCosts(costs.map((cc, i2) => i2 === idx ? { ...cc, supply_item_index: e.target.value === '' ? null : parseInt(e.target.value) } : cc))}
                        className="col-span-3 px-2 py-1.5 border border-fg-subtle/30 rounded text-xs bg-bg">
                  <option value="">— SKU —</option>
                  {items.map((i, i2) => (
                    <option key={i2} value={i2}>{i.offer_id || `#${i2 + 1}`}</option>
                  ))}
                </select>
              ) : <div className="col-span-3" />}
              <input value={c.note ?? ''}
                     onChange={(e) => setCosts(costs.map((cc, i2) => i2 === idx ? { ...cc, note: e.target.value || null } : cc))}
                     placeholder="заметка" className="col-span-1 px-2 py-1.5 border border-fg-subtle/30 rounded text-xs bg-bg" />
              <button onClick={() => setCosts(costs.filter((_, i2) => i2 !== idx))}
                      className="col-span-1 text-fg-muted hover:text-rose-600">
                <Trash2 className="size-4" />
              </button>
            </div>
          ))}
          {totalCostsSum > 0 && (
            <div className="mt-2 px-3 py-2 bg-bg-subtle/40 rounded text-xs">
              <div>Σ затрат всего (справочно): <b>{formatCurrency(totalCostsSum)}</b></div>
              <div>Σ на всю поставку: <b>{formatCurrency(sumSupply)}</b></div>
              <div className="text-fg-muted mt-1">Эти суммы НЕ записываются в себестоимость автоматически. Используй для ручного пересчёта final_unit_cost.</div>
            </div>
          )}
        </div>

        {/* Документы */}
        <div className="mb-4">
          <div className="text-xs font-medium text-fg-muted uppercase mb-2 flex items-center gap-1">
            <Paperclip className="size-3" /> Документы
          </div>
          {editingId && editing && editing.documents.length > 0 && (
            <div className="mb-2 space-y-1">
              {editing.documents.map(d => (
                <DocChip key={d.id} doc={d} supplyId={editingId} />
              ))}
            </div>
          )}
          <DropZone
            onFiles={(files, scope, itemIdx) => {
              setPendingFiles([
                ...pendingFiles,
                ...files.map(f => ({ file: f, scope, itemIdx })),
              ])
            }}
            items={items}
          />
          {pendingFiles.length > 0 && (
            <div className="mt-2 space-y-1">
              {pendingFiles.map((pf, idx) => (
                <div key={idx} className="flex items-center justify-between px-2 py-1 bg-bg-subtle/40 rounded text-xs">
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
              <div className="text-[10px] text-fg-muted">Загрузятся после нажатия «Сохранить»</div>
            </div>
          )}
        </div>

        {/* Заметки */}
        <div className="mb-4">
          <label className="text-xs text-fg-muted uppercase block mb-1">Общие заметки</label>
          <textarea value={form.notes}
                    onChange={(e) => setForm({ ...form, notes: e.target.value })}
                    placeholder="что-то особенное по этой поставке…"
                    rows={2}
                    className="w-full px-3 py-2 border border-fg-subtle/30 rounded-lg text-sm bg-bg" />
        </div>

        {error && <p className="text-sm text-rose-600 mb-3">{error}</p>}

        <div className="flex justify-end gap-2">
          <button onClick={onClose}
                  className="px-4 py-2 text-sm border border-fg-subtle/30 rounded-lg hover:bg-bg-subtle/30">
            Отмена
          </button>
          <button onClick={save}
                  disabled={!form.name || saving}
                  className="px-4 py-2 bg-accent text-white text-sm rounded-lg hover:bg-accent-hover disabled:opacity-50">
            {saving ? 'Сохраняю…' : (editingId ? 'Сохранить' : 'Создать')}
          </button>
        </div>
      </div>
    </div>
  )
}

function DropZone({ onFiles, items }: {
  onFiles: (files: File[], scope: 'supply' | 'item', itemIdx: number | null) => void
  items: SupplyItem[]
}) {
  const [drag, setDrag] = useState(false)
  const [scope, setScope] = useState<'supply' | 'item'>('supply')
  const [itemIdx, setItemIdx] = useState<number | null>(null)

  return (
    <div className="space-y-2">
      <div className="flex gap-2 items-center text-xs">
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
          'border-2 border-dashed rounded-md p-4 text-center text-xs cursor-pointer',
          drag ? 'border-accent bg-accent/5' : 'border-fg-subtle/30 hover:bg-bg-subtle/30',
        )}
        onClick={() => document.getElementById('supply-file-input')?.click()}
      >
        <Upload className="size-4 mx-auto mb-1 text-fg-muted" />
        Перетащи файлы сюда или нажми для выбора (pdf, jpg, png, xlsx, docx; до 25 МБ)
        <input id="supply-file-input" type="file" multiple hidden
               onChange={(e) => {
                 const files = Array.from(e.target.files || [])
                 if (files.length) onFiles(files, scope, scope === 'item' ? itemIdx : null)
               }} />
      </div>
    </div>
  )
}

function Field({ label, value, onChange, placeholder, type = 'text' }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string
}) {
  return (
    <div>
      <label className="text-[10px] text-fg-muted uppercase block mb-1">{label}</label>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)}
             placeholder={placeholder}
             className="w-full px-2 py-1.5 border border-fg-subtle/30 rounded text-sm bg-bg" />
    </div>
  )
}
