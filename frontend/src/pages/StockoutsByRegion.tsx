import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MapPin, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatNumber, cn } from '@/lib/utils'

interface ClusterRow {
  cluster: string
  stockout_skus: number
  reorder_now_skus: number
  ok_skus: number
  total_free_to_sell: number
  velocity_per_day: number
}

interface ClustersResp {
  clusters: ClusterRow[]
}

export function StockoutsByRegion() {
  const { data, isLoading } = useQuery<ClustersResp>({
    queryKey: ['warehouse-stocks', 'clusters'],
    queryFn: async () => (await api.get('/warehouse-stocks/clusters')).data,
  })

  const totalStockout = (data?.clusters || []).reduce((s, c) => s + c.stockout_skus, 0)
  const totalRisks = (data?.clusters || []).reduce((s, c) => s + c.reorder_now_skus, 0)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Стокауты по регионам</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          {totalStockout} товаров в стокауте · {totalRisks} с риском в ближайшие 7 дней
        </p>
      </div>

      {isLoading ? (
        <Card className="py-16 flex justify-center items-center text-fg-muted">
          <Loader2 className="w-5 h-5 animate-spin mr-2" /> Загрузка…
        </Card>
      ) : (data?.clusters.length ?? 0) === 0 ? (
        <Card className="py-12 flex flex-col items-center text-fg-muted text-sm">
          <MapPin className="w-8 h-8 mb-2 text-fg-subtle" />
          <p>Нет данных по складам — запустите sync_all_warehouse_stocks</p>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                  <th className="py-2.5 px-4 font-medium">кластер</th>
                  <th className="py-2.5 px-4 font-medium text-right">🔴 стокаут</th>
                  <th className="py-2.5 px-4 font-medium text-right">🟡 пора</th>
                  <th className="py-2.5 px-4 font-medium text-right">🟢 норма</th>
                  <th className="py-2.5 px-4 font-medium text-right">всего остатка</th>
                  <th className="py-2.5 px-4 font-medium text-right">скорость/день</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {data!.clusters.map((c) => (
                  <tr key={c.cluster} className="hover:bg-bg-subtle/40">
                    <td className="py-2.5 px-4">
                      <div className="flex items-center gap-2">
                        <MapPin className="w-4 h-4 text-fg-subtle" />
                        <span className="font-medium text-fg">{c.cluster}</span>
                      </div>
                    </td>
                    <td className={cn('py-2.5 px-4 text-right tabular-nums font-semibold',
                      c.stockout_skus > 0 ? 'text-rose-700' : 'text-fg-subtle')}>
                      {c.stockout_skus}
                    </td>
                    <td className={cn('py-2.5 px-4 text-right tabular-nums',
                      c.reorder_now_skus > 0 ? 'text-amber-700 font-semibold' : 'text-fg-subtle')}>
                      {c.reorder_now_skus}
                    </td>
                    <td className="py-2.5 px-4 text-right tabular-nums text-emerald-700">{c.ok_skus}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums">{formatNumber(c.total_free_to_sell)}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums text-fg-muted">
                      {c.velocity_per_day.toFixed(1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
