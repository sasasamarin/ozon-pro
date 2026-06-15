import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Megaphone, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'

interface Row {
  cabinet_id: string
  cabinet_name: string
  ozon_campaign_id: string | null
  title: string | null
  status: string | null
  placement: string | null
  views: number
  clicks: number
  ctr: number
  click_price: number
  money_spent: number
  orders: number
  orders_money: number
  drr: number
  to_cart: number
}

interface Resp {
  rows: Row[]
  total_spend: number
  total_orders_money: number
  drr_pct: number | null
  skipped_cabinets: string[]
  source: string
  note: string
}

export function AdsCampaigns() {
  const [activeOnly, setActiveOnly] = useState(true)
  const { data, isLoading } = useQuery<Resp>({
    queryKey: ['ads-campaign-stats', activeOnly],
    queryFn: async () =>
      (await api.get(`/ads/campaign-stats?active_only=${activeOnly}`)).data,
  })

  const rows = data?.rows ?? []

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Реклама «Оплата за клик»</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            По кампаниям · {rows.length} строк {data?.note ? `· ${data.note}` : ''}
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-fg-muted cursor-pointer">
          <input
            type="checkbox"
            checked={activeOnly}
            onChange={(e) => setActiveOnly(e.target.checked)}
            className="accent-indigo-600"
          />
          только активные
        </label>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Card className="p-4">
          <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">Расход на рекламу</p>
          <p className="text-[22px] font-semibold text-rose-700 mt-1 tabular-nums">
            {formatCurrency(data?.total_spend ?? 0)}
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">Продажи с рекламы</p>
          <p className="text-[22px] font-semibold text-emerald-700 mt-1 tabular-nums">
            {formatCurrency(data?.total_orders_money ?? 0)}
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">ДРР (общий)</p>
          <p className="text-[22px] font-semibold text-indigo-700 mt-1 tabular-nums">
            {data?.drr_pct != null ? `${data.drr_pct}%` : '—'}
          </p>
        </Card>
      </div>

      {data?.skipped_cabinets?.length ? (
        <p className="text-xs text-amber-700">
          Пропущены кабинеты без Performance API: {data.skipped_cabinets.join(', ')}
        </p>
      ) : null}

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 flex justify-center text-fg-muted"><Loader2 className="w-5 h-5 animate-spin" /></div>
        ) : rows.length === 0 ? (
          <div className="py-16 flex flex-col items-center gap-2 text-fg-muted">
            <Megaphone className="w-6 h-6 opacity-40" />
            <span className="text-sm">Нет кампаний с данными</span>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle/50 border-b border-border-subtle text-fg-muted">
                <tr>
                  <th className="py-2.5 px-4 font-medium text-left">кампания</th>
                  <th className="py-2.5 px-4 font-medium text-left">кабинет</th>
                  <th className="py-2.5 px-4 font-medium text-right">показы</th>
                  <th className="py-2.5 px-4 font-medium text-right">клики</th>
                  <th className="py-2.5 px-4 font-medium text-right">CTR</th>
                  <th className="py-2.5 px-4 font-medium text-right">расход</th>
                  <th className="py-2.5 px-4 font-medium text-right">заказы</th>
                  <th className="py-2.5 px-4 font-medium text-right">продажи</th>
                  <th className="py-2.5 px-4 font-medium text-right">ДРР</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={`${r.ozon_campaign_id}-${i}`} className="border-b border-border-subtle/60 hover:bg-bg-subtle/40">
                    <td className="py-2.5 px-4">
                      <div className="font-medium text-fg">{r.title || r.ozon_campaign_id}</div>
                      {r.status ? <div className="text-[11px] text-fg-muted">{r.status}</div> : null}
                    </td>
                    <td className="py-2.5 px-4 text-fg-muted">{r.cabinet_name}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums">{formatNumber(r.views)}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums">{formatNumber(r.clicks)}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums text-fg-muted">{r.ctr}%</td>
                    <td className="py-2.5 px-4 text-right tabular-nums text-rose-700">{formatCurrency(r.money_spent)}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums">{formatNumber(r.orders)}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums text-emerald-700">{formatCurrency(r.orders_money)}</td>
                    <td className={cn('py-2.5 px-4 text-right tabular-nums font-semibold',
                      r.drr > 15 ? 'text-rose-700' : r.drr > 0 ? 'text-fg' : 'text-fg-muted')}>
                      {r.drr}%
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
