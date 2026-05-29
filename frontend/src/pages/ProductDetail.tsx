import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  MapPin,
  Image as ImageIcon,
  Loader2,
  Save,
  Truck,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { StockSalesChart } from '@/components/StockSalesChart'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'

interface WarehouseRow {
  warehouse_name: string | null
  warehouse_id: number | null
  city: string | null
  cluster: string | null
  free_to_sell: number
  reserved: number
  in_transit: number
  velocity_per_day: number
  days_left: number | null
  signal: 'stockout' | 'reorder_now' | 'ok'
}

interface ProductWarehouseStocks {
  product_id: string
  product_name: string
  offer_id: string
  total_free_to_sell: number
  rows: WarehouseRow[]
  snapshot_at: string | null
}

interface SupplyRow {
  product_id: string
  lead_time_total_days: number
  lead_time_production_days: number | null
  lead_time_delivery_days: number | null
  lead_time_processing_days: number | null
  moq: number
  batch_step: number
  batch_strict: boolean
  safety_stock_days: number
  longterm_window_days: number
  shortterm_window_days: number
  forecast_strategy: string
  has_record: boolean
}

const SIGNAL_META: Record<string, { dot: string; label: string }> = {
  stockout: { dot: 'bg-rose-500', label: 'Стокаут' },
  reorder_now: { dot: 'bg-amber-500', label: 'Пора заказывать' },
  ok: { dot: 'bg-emerald-500', label: 'Норма' },
}

export function ProductDetail() {
  const { id } = useParams<{ id: string }>()
  const qc = useQueryClient()

  const { data: warehouses, isLoading } = useQuery<ProductWarehouseStocks>({
    queryKey: ['warehouse-stocks', 'product', id],
    queryFn: async () =>
      (await api.get(`/warehouse-stocks/products/${id}`)).data,
    enabled: !!id,
  })

  const { data: supplyAll } = useQuery<SupplyRow[]>({
    queryKey: ['supply-params', 'list'],
    queryFn: async () => (await api.get('/supply-params/')).data,
  })

  const supply = supplyAll?.find((s) => s.product_id === id)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link to="/products" className="inline-flex items-center text-sm text-fg-muted hover:text-fg gap-1">
          <ArrowLeft className="w-4 h-4" /> Все товары
        </Link>
      </div>

      {/* Header */}
      <Card className="p-5 flex items-start gap-4">
        <div className="w-20 h-20 rounded-lg bg-bg-subtle flex items-center justify-center shrink-0 overflow-hidden border border-border-subtle">
          <ImageIcon className="w-8 h-8 text-fg-subtle" />
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-semibold text-fg tracking-tight leading-snug">
            {warehouses?.product_name || 'Загрузка…'}
          </h1>
          <p className="text-sm text-fg-muted font-mono mt-1">{warehouses?.offer_id}</p>
          <div className="flex items-center gap-4 mt-3 text-sm">
            <div>
              <span className="text-fg-muted">Всего остаток:</span>{' '}
              <span className="font-semibold text-fg tabular-nums">{formatNumber(warehouses?.total_free_to_sell ?? 0)} шт</span>
            </div>
            <div>
              <span className="text-fg-muted">Складов:</span>{' '}
              <span className="font-semibold text-fg tabular-nums">{warehouses?.rows.length ?? 0}</span>
            </div>
          </div>
        </div>
      </Card>

      {/* Warehouse stocks */}
      <Card className="overflow-hidden">
        <div className="px-6 py-4 border-b border-border-subtle flex items-center justify-between flex-wrap">
          <div>
            <h2 className="text-base font-semibold text-fg flex items-center gap-2">
              <MapPin className="w-4 h-4 text-fg-muted" />
              Остатки по складам
            </h2>
            <p className="text-xs text-fg-muted mt-0.5">
              Скорость — заказы из этого склада за 30 дней / день
            </p>
          </div>
        </div>
        {isLoading ? (
          <div className="py-12 flex justify-center text-fg-muted">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : (warehouses?.rows.length ?? 0) === 0 ? (
          <div className="py-12 text-center text-sm text-fg-muted">
            Нет данных по складам — запустите sync_warehouse_stocks
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                  <th className="py-2.5 px-4 font-medium">город</th>
                  <th className="py-2.5 px-4 font-medium">кластер</th>
                  <th className="py-2.5 px-4 font-medium text-right">остаток</th>
                  <th className="py-2.5 px-4 font-medium text-right">резерв</th>
                  <th className="py-2.5 px-4 font-medium text-right">в пути</th>
                  <th className="py-2.5 px-4 font-medium text-right">скорость/д</th>
                  <th className="py-2.5 px-4 font-medium text-right">дни до конца</th>
                  <th className="py-2.5 px-4 font-medium">статус</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {warehouses!.rows.map((r) => {
                  const meta = SIGNAL_META[r.signal]
                  return (
                    <tr key={r.warehouse_name} className="hover:bg-bg-subtle/40">
                      <td className="py-2.5 px-4 text-fg">{r.city || r.warehouse_name || '—'}</td>
                      <td className="py-2.5 px-4 text-fg-muted">{r.cluster || '—'}</td>
                      <td className={cn(
                        'py-2.5 px-4 text-right tabular-nums font-semibold',
                        r.signal === 'stockout' && 'text-rose-700',
                        r.signal === 'reorder_now' && 'text-amber-700',
                      )}>
                        {formatNumber(r.free_to_sell)}
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums text-fg-muted">{formatNumber(r.reserved)}</td>
                      <td className="py-2.5 px-4 text-right tabular-nums text-fg-muted">{formatNumber(r.in_transit)}</td>
                      <td className="py-2.5 px-4 text-right tabular-nums">{r.velocity_per_day.toFixed(1)}</td>
                      <td className="py-2.5 px-4 text-right tabular-nums">
                        {r.days_left != null ? `${r.days_left}` : '—'}
                      </td>
                      <td className="py-2.5 px-4">
                        <span className="inline-flex items-center gap-1.5 text-xs">
                          <span className={cn('inline-block w-2 h-2 rounded-full', meta.dot)} />
                          {meta.label}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Supply params */}
      {supply && (
        <Card className="p-5">
          <h2 className="text-base font-semibold text-fg flex items-center gap-2">
            <Truck className="w-4 h-4 text-fg-muted" />
            Параметры поставки
          </h2>
          <p className="text-xs text-fg-muted mt-0.5">
            Lead time, MOQ, страховой запас. Для штучной правки — перейдите в /supply-params.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
            <Stat label="Lead time" value={`${supply.lead_time_total_days} дн`} />
            <Stat label="Страх. запас" value={`${supply.safety_stock_days} дн`} />
            <Stat label="MOQ" value={formatNumber(supply.moq)} />
            <Stat label="Кратность" value={`${supply.batch_step}${supply.batch_strict ? ' (строгая)' : ''}`} />
          </div>
          <div className="mt-4">
            <Link to="/supply-params" className="text-sm text-indigo-700 hover:underline">
              Открыть форму параметров поставки →
            </Link>
          </div>
        </Card>
      )}

      <StockSalesChart productId={id!} />
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border-subtle bg-bg-subtle/30 px-3 py-2">
      <div className="text-[10px] font-medium text-fg-muted uppercase tracking-wider">{label}</div>
      <div className="text-sm font-semibold text-fg mt-0.5 tabular-nums">{value}</div>
    </div>
  )
}
