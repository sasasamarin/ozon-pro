import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FolderTree, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'

interface CategoryRow {
  category_name: string
  sku_count: number
  revenue: number
  delivered_units: number
  cogs: number
  gross_profit: number
  gross_margin_pct: number | null
  revenue_share_pct: number
}

interface Resp {
  period_from: string
  period_to: string
  total_revenue: number
  rows: CategoryRow[]
}

export function Categories() {
  const { selectedCabinetIds } = useCabinetStore()
  const [days, setDays] = useState(30)

  const { data, isLoading } = useQuery<Resp>({
    queryKey: ['categories', selectedCabinetIds, days],
    queryFn: async () => {
      const p = new URLSearchParams({ days: String(days) })
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      return (await api.get(`/products/categories/?${p.toString()}`)).data
    },
  })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Категории</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            {data?.rows.length ?? 0} категорий · общая выручка {formatCurrency(data?.total_revenue ?? 0)}
          </p>
        </div>
        <div className="flex gap-2">
          {[7, 28, 30, 90, 365].map((d) => (
            <button key={d} onClick={() => setDays(d)} className={cn(
              'px-3 py-1.5 rounded-md text-sm border transition-colors',
              days === d ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
            )}>
              {d === 7 && '7 дней'}{d === 30 && '30 дней'}{d === 90 && '90 дней'}{d === 365 && 'Год'}
            </button>
          ))}
        </div>
      </div>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 flex justify-center text-fg-muted"><Loader2 className="w-5 h-5 animate-spin" /></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                  <th className="py-2.5 px-4 font-medium">категория</th>
                  <th className="py-2.5 px-4 font-medium text-right">SKU</th>
                  <th className="py-2.5 px-4 font-medium text-right">шт продано</th>
                  <th className="py-2.5 px-4 font-medium text-right">выручка</th>
                  <th className="py-2.5 px-4 font-medium text-right">доля</th>
                  <th className="py-2.5 px-4 font-medium text-right">COGS</th>
                  <th className="py-2.5 px-4 font-medium text-right">валовая</th>
                  <th className="py-2.5 px-4 font-medium text-right">маржа %</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {(data?.rows || []).map((r) => (
                  <tr key={r.category_name} className="hover:bg-bg-subtle/40">
                    <td className="py-2.5 px-4">
                      <div className="flex items-center gap-2">
                        <FolderTree className="w-4 h-4 text-fg-subtle" />
                        <span className="text-fg">{r.category_name}</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-4 text-right tabular-nums">{r.sku_count}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums">{formatNumber(r.delivered_units)}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums text-emerald-700">{formatCurrency(r.revenue)}</td>
                    <td className="py-2.5 px-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-16 h-2 bg-bg-subtle rounded">
                          <div className="h-full bg-emerald-400 rounded" style={{ width: `${Math.min(100, r.revenue_share_pct)}%` }} />
                        </div>
                        <span className="text-xs text-fg-muted tabular-nums w-10 text-right">{r.revenue_share_pct}%</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-4 text-right tabular-nums text-rose-700">−{formatCurrency(r.cogs)}</td>
                    <td className={cn('py-2.5 px-4 text-right tabular-nums font-semibold',
                      r.gross_profit >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
                      {formatCurrency(r.gross_profit)}
                    </td>
                    <td className="py-2.5 px-4 text-right tabular-nums">
                      {r.gross_margin_pct != null ? `${r.gross_margin_pct}%` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
