import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Grid3x3, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'

interface RecRow {
  product_id: string
  product_name: string
  offer_id: string
  current_price: number | null
  cost_price: number | null
  current_stock: number
  velocity: { adjusted_daily: number; total_units_sold: number }
  buyout: { rate: number }
  procurement: { recommended_qty: number; signal: string } | null
  abc_class: string | null
}

/** Treemap-подобная карта товаров: площадь = выручка 30д, цвет = маржа */
export function Heatmap() {
  const { selectedCabinetIds } = useCabinetStore()
  const { data, isLoading } = useQuery<RecRow[]>({
    queryKey: ['recommendations', selectedCabinetIds, 'heatmap'],
    queryFn: async () => {
      const p = new URLSearchParams()
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      const qs = p.toString() ? `?${p.toString()}` : ''
      return (await api.get(`/recommendations/products${qs}`, { timeout: 60000 })).data
    },
    staleTime: 60_000,
  })

  const items = useMemo(() => {
    if (!data) return []
    // Считаем revenue 30д ≈ units_sold × price (по velocity * 28 за 28д)
    return data
      .map((p) => {
        const units = p.velocity.total_units_sold
        const revenue = (p.current_price || 0) * units
        const grossPerUnit =
          (p.current_price || 0) - (p.cost_price || 0) - (p.current_price || 0) * 0.25 // ≈ комиссия 25%
        const marginPct = (p.current_price || 0) > 0 ? (grossPerUnit / (p.current_price || 1)) * 100 : 0
        return { ...p, revenue, marginPct, units }
      })
      .filter((p) => p.revenue > 0)
      .sort((a, b) => b.revenue - a.revenue)
  }, [data])

  const maxRevenue = items[0]?.revenue || 1

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Карта товаров</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          Размер плитки — выручка 28 дней. Цвет — маржа (зелёный высокая, красный низкая)
        </p>
      </div>

      {isLoading ? (
        <Card className="py-16 flex justify-center text-fg-muted"><Loader2 className="w-5 h-5 animate-spin" /></Card>
      ) : items.length === 0 ? (
        <Card className="py-12 flex flex-col items-center text-fg-muted">
          <Grid3x3 className="w-8 h-8 mb-2 text-fg-subtle" />
          <p className="text-sm">Нет товаров с выручкой</p>
        </Card>
      ) : (
        <Card className="p-4">
          <div className="grid auto-rows-[minmax(80px,auto)] gap-2"
               style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))' }}>
            {items.map((p) => {
              const size = Math.max(1, Math.min(4, Math.ceil((p.revenue / maxRevenue) * 4)))
              const marginColor =
                p.marginPct >= 40 ? 'bg-emerald-100 border-emerald-300 text-emerald-900' :
                p.marginPct >= 20 ? 'bg-lime-100 border-lime-300 text-lime-900' :
                p.marginPct >= 0 ? 'bg-amber-100 border-amber-300 text-amber-900' :
                'bg-rose-100 border-rose-300 text-rose-900'
              return (
                <Link
                  key={p.product_id}
                  to={`/products/${p.product_id}`}
                  className={cn(
                    'rounded-lg border p-3 hover:shadow-elev transition-all',
                    marginColor,
                  )}
                  style={{ gridColumn: `span ${size}`, gridRow: `span ${Math.min(2, size)}` }}
                >
                  <div className="text-[11px] font-mono opacity-70 truncate">{p.offer_id}</div>
                  <div className="text-sm font-medium mt-0.5 line-clamp-2">{p.product_name}</div>
                  <div className="mt-2 flex items-baseline justify-between gap-1">
                    <span className="text-xs opacity-80">маржа</span>
                    <span className="text-base font-bold tabular-nums">{p.marginPct.toFixed(0)}%</span>
                  </div>
                  <div className="text-xs opacity-80 tabular-nums">{formatCurrency(p.revenue)}</div>
                </Link>
              )
            })}
          </div>
        </Card>
      )}
    </div>
  )
}
