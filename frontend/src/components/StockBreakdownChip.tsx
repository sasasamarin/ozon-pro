/**
 * Чип "X шт" с поповером — при hover/click показывает разбивку по складам и кластерам.
 * Источник: GET /products/{id}/stock-details (единая функция get_stock).
 * Юзер хотел: "тултип/раскрытие: Всего 535 шт: Москва 200, СПб 150..."
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, MapPin } from 'lucide-react'
import { api } from '@/lib/api'
import { formatNumber, cn } from '@/lib/utils'

interface StockDetailsRow {
  warehouse_type: string
  warehouse_name: string | null
  city: string | null
  cluster: string | null
  free_to_sell: number
  reserved: number
  in_transit: number
  available: number
}

interface StockDetailsResp {
  total_free_to_sell: number
  total_reserved: number
  total_in_transit: number
  total_available: number
  by_warehouse: StockDetailsRow[]
  by_cluster: { cluster: string; available: number }[]
  by_type: Record<string, number>
  snapshot_at: string | null
  has_per_warehouse: boolean
}

export function StockBreakdownChip({
  productId,
  totalAvailable,
  alignRight = false,
}: {
  productId: string
  totalAvailable: number
  alignRight?: boolean
}) {
  const [open, setOpen] = useState(false)
  const { data, isLoading } = useQuery<StockDetailsResp>({
    queryKey: ['product', productId, 'stock-details'],
    queryFn: async () =>
      (await api.get(`/products/${productId}/stock-details`)).data,
    enabled: open,
    staleTime: 60_000,
  })

  const color =
    totalAvailable === 0 ? 'text-rose-700' :
    totalAvailable < 10 ? 'text-amber-700' :
    'text-fg'

  return (
    <div className="relative inline-block">
      <button
        onClick={(e) => {
          e.stopPropagation()
          setOpen((v) => !v)
        }}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className={cn(
          'tabular-nums font-semibold hover:underline cursor-help',
          color,
        )}
      >
        {formatNumber(totalAvailable)}
      </button>
      {open && (
        <div
          onMouseEnter={() => setOpen(true)}
          onMouseLeave={() => setOpen(false)}
          className={cn(
            'absolute z-50 top-6 min-w-[300px] max-w-[420px] bg-surface border border-border rounded-lg shadow-xl p-3',
            alignRight ? 'right-0' : 'left-0',
          )}
        >
          {isLoading || !data ? (
            <div className="flex items-center gap-2 text-sm text-fg-muted py-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Загружаю разбивку…
            </div>
          ) : (
            <div className="space-y-2 text-xs">
              <div className="flex items-center justify-between pb-1.5 border-b border-border-subtle">
                <span className="font-semibold text-fg flex items-center gap-1.5">
                  <MapPin className="w-3 h-3" />
                  Остаток {formatNumber(data.total_available)} шт
                </span>
                <span className="text-fg-muted">
                  свободно {formatNumber(data.total_free_to_sell)}
                  {data.total_reserved > 0 && ` − резерв ${data.total_reserved}`}
                </span>
              </div>

              {data.by_cluster.length > 0 && (
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-fg-muted mb-1">по кластерам</div>
                  <div className="flex flex-wrap gap-1">
                    {data.by_cluster.map((c) => (
                      <span key={c.cluster}
                            className="px-1.5 py-0.5 rounded bg-bg-subtle text-fg tabular-nums">
                        {c.cluster}: <strong>{c.available}</strong>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {data.by_warehouse.length > 0 && (
                <div className="max-h-[180px] overflow-y-auto">
                  <div className="text-[10px] uppercase tracking-wider text-fg-muted mb-1">по складам</div>
                  <table className="w-full">
                    <tbody>
                      {data.by_warehouse.map((w, i) => (
                        <tr key={i} className="text-fg">
                          <td className="py-0.5 pr-2 truncate max-w-[180px]">
                            {w.warehouse_name === '<aggregate>'
                              ? <span className="text-fg-muted">{w.warehouse_type} (агрегат)</span>
                              : (w.city || w.warehouse_name || '—')}
                          </td>
                          <td className="py-0.5 px-1 text-fg-muted text-[10px]">
                            {w.warehouse_type === 'FBO_WH' ? 'FBO' : w.warehouse_type}
                          </td>
                          <td className="py-0.5 pl-2 text-right tabular-nums">
                            {w.available}
                            {w.reserved > 0 && (
                              <span className="text-fg-muted">  ({w.reserved} рез.)</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {data.total_in_transit > 0 && (
                <div className="text-fg-muted pt-1 border-t border-border-subtle">
                  В пути: <span className="text-fg tabular-nums">{formatNumber(data.total_in_transit)} шт</span>
                </div>
              )}

              {!data.has_per_warehouse && (
                <div className="text-amber-700 text-[10px] pt-1">
                  Per-warehouse данных нет — показываем агрегаты FBO/FBS/RFBS.
                </div>
              )}

              {data.snapshot_at && (
                <div className="text-[10px] text-fg-subtle">
                  Снапшот: {new Date(data.snapshot_at).toLocaleString('ru-RU', {
                    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
