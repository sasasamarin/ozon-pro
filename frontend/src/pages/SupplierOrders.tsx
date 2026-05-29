import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Package, Plus, Loader2, CheckCircle2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'

interface OrderRow {
  id: string
  supplier_id: string | null
  supplier_name: string | null
  product_id: string
  product_name: string
  offer_id: string
  qty: number
  unit_price: number
  delivery_cost: number
  total: number
  order_date: string
  expected_date: string | null
  received_date: string | null
  status: string
}

interface ProductLite {
  id: string
  name: string
  offer_id: string
}

const STATUS_META: Record<string, { label: string; cls: string }> = {
  created: { label: 'Создан', cls: 'bg-fg-subtle/10 text-fg-muted' },
  paid: { label: 'Оплачен', cls: 'bg-blue-50 text-blue-700' },
  in_transit: { label: 'В пути', cls: 'bg-amber-50 text-amber-700' },
  received: { label: 'Получен', cls: 'bg-emerald-50 text-emerald-700' },
  partial: { label: 'Частично', cls: 'bg-violet-50 text-violet-700' },
}

export function SupplierOrders() {
  const qc = useQueryClient()
  const [filter, setFilter] = useState('')
  const [showForm, setShowForm] = useState(false)

  const { data: orders, isLoading } = useQuery<OrderRow[]>({
    queryKey: ['supplier-orders', filter],
    queryFn: async () => {
      const q = filter ? `?status=${filter}` : ''
      return (await api.get(`/procurement/orders/${q}`)).data
    },
  })

  const { data: products } = useQuery<ProductLite[]>({
    queryKey: ['products', 'lite'],
    queryFn: async () => {
      const all = (await api.get('/products/')).data as Array<{ id: string; name: string; offer_id: string }>
      return all.map((p) => ({ id: p.id, name: p.name, offer_id: p.offer_id }))
    },
  })

  const [productId, setProductId] = useState('')
  const [qty, setQty] = useState('')
  const [unitPrice, setUnitPrice] = useState('')
  const [deliveryCost, setDeliveryCost] = useState('0')
  const [orderDate, setOrderDate] = useState(new Date().toISOString().slice(0, 10))
  const [expectedDate, setExpectedDate] = useState('')

  const create = useMutation({
    mutationFn: async () => (await api.post('/procurement/orders/', {
      product_id: productId,
      qty: parseInt(qty || '0', 10),
      unit_price: parseFloat(unitPrice || '0'),
      delivery_cost: parseFloat(deliveryCost || '0'),
      order_date: orderDate,
      expected_date: expectedDate || null,
    })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['supplier-orders'] })
      setShowForm(false)
      setProductId(''); setQty(''); setUnitPrice('')
    },
  })

  const markReceived = useMutation({
    mutationFn: async (id: string) => (await api.patch(`/procurement/orders/${id}`, {
      status: 'received',
    })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['supplier-orders'] })
      qc.invalidateQueries({ queryKey: ['costs'] })
      qc.invalidateQueries({ queryKey: ['recommendations'] })
    },
  })

  const totalOpen = (orders || []).filter((o) => o.status !== 'received')
    .reduce((s, o) => s + o.total, 0)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Заказы поставщикам</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Активных в работе: {formatCurrency(totalOpen)}
          </p>
        </div>
        <div className="flex gap-2">
          {['', 'created', 'paid', 'in_transit', 'received'].map((s) => (
            <button key={s} onClick={() => setFilter(s)} className={cn(
              'px-3 py-1.5 rounded-md text-sm border transition-colors',
              filter === s ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
            )}>
              {s === '' ? 'Все' : STATUS_META[s]?.label}
            </button>
          ))}
          <Button onClick={() => setShowForm((v) => !v)}>
            <Plus className="w-4 h-4" /> Заказ
          </Button>
        </div>
      </div>

      {showForm && (
        <Card className="p-5">
          <h3 className="text-base font-semibold text-fg mb-4">Новый заказ поставщику</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <div className="md:col-span-2">
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Товар</label>
              <select value={productId} onChange={(e) => setProductId(e.target.value)}
                className="h-9 px-3 rounded-md border border-border bg-surface text-sm w-full">
                <option value="">— выбрать —</option>
                {(products || []).map((p) => (
                  <option key={p.id} value={p.id}>{p.offer_id} · {p.name.slice(0, 40)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Количество</label>
              <Input type="number" value={qty} onChange={(e) => setQty(e.target.value)} />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Цена/шт ₽</label>
              <Input type="number" value={unitPrice} onChange={(e) => setUnitPrice(e.target.value)} />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Доставка ₽</label>
              <Input type="number" value={deliveryCost} onChange={(e) => setDeliveryCost(e.target.value)} />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Дата заказа</label>
              <Input type="date" value={orderDate} onChange={(e) => setOrderDate(e.target.value)} />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Ожидаемая дата</label>
              <Input type="date" value={expectedDate} onChange={(e) => setExpectedDate(e.target.value)} />
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="ghost" onClick={() => setShowForm(false)}>Отмена</Button>
            <Button onClick={() => create.mutate()} disabled={create.isPending || !productId || !qty || !unitPrice}>
              {create.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Создать'}
            </Button>
          </div>
        </Card>
      )}

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 flex justify-center text-fg-muted"><Loader2 className="w-5 h-5 animate-spin" /></div>
        ) : (orders?.length ?? 0) === 0 ? (
          <div className="py-12 flex flex-col items-center text-fg-muted text-sm">
            <Package className="w-8 h-8 mb-2 text-fg-subtle" />
            <p>Заказов поставщикам пока нет</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                  <th className="py-2.5 px-4 font-medium">дата</th>
                  <th className="py-2.5 px-4 font-medium">товар</th>
                  <th className="py-2.5 px-4 font-medium text-right">кол-во</th>
                  <th className="py-2.5 px-4 font-medium text-right">цена</th>
                  <th className="py-2.5 px-4 font-medium text-right">итог</th>
                  <th className="py-2.5 px-4 font-medium">ожидание</th>
                  <th className="py-2.5 px-4 font-medium">статус</th>
                  <th className="py-2.5 px-4 font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {(orders || []).map((o) => {
                  const meta = STATUS_META[o.status] || { label: o.status, cls: '' }
                  return (
                    <tr key={o.id} className="hover:bg-bg-subtle/40">
                      <td className="py-2.5 px-4 text-fg-muted tabular-nums">{o.order_date}</td>
                      <td className="py-2.5 px-4">
                        <div className="text-fg truncate max-w-[260px]">{o.product_name}</div>
                        <div className="text-xs text-fg-muted font-mono">{o.offer_id}</div>
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums">{formatNumber(o.qty)}</td>
                      <td className="py-2.5 px-4 text-right tabular-nums">{formatCurrency(o.unit_price)}</td>
                      <td className="py-2.5 px-4 text-right tabular-nums font-semibold">{formatCurrency(o.total)}</td>
                      <td className="py-2.5 px-4 text-fg-muted text-xs">{o.expected_date || '—'}</td>
                      <td className="py-2.5 px-4">
                        <span className={cn('text-xs font-medium px-1.5 py-0.5 rounded', meta.cls)}>{meta.label}</span>
                      </td>
                      <td className="py-2.5 px-2">
                        {o.status !== 'received' && (
                          <button onClick={() => markReceived.mutate(o.id)}
                            className="text-xs text-emerald-700 hover:underline inline-flex items-center gap-1">
                            <CheckCircle2 className="w-3.5 h-3.5" /> получен
                          </button>
                        )}
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
