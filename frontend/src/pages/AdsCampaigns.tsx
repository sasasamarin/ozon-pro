import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Megaphone, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'

interface CampaignRow {
  cabinet_name: string
  ozon_campaign_id: string | null
  title: string | null
  status: string | null
  views: number
  clicks: number
  ctr: number
  money_spent: number
  orders: number
  orders_money: number
  drr: number
}
interface CampaignResp {
  rows: CampaignRow[]
  total_spend: number
  total_orders_money: number
  drr_pct: number | null
  skipped_cabinets: string[]
  note: string
}

interface SkuRow {
  cabinet_name: string
  sku: string
  product_name: string | null
  views: number
  clicks: number
  ctr: number
  avg_cpc: number
  spend: number
  orders: number
  sales: number
  drr: number
}
interface SkuResp {
  date: string
  rows: SkuRow[]
  total_spend: number
  total_sales: number
  drr_pct: number | null
  matched_to_products: number
  skipped_cabinets: string[]
  note: string
}

type Mode = 'campaigns' | 'products'

export function AdsCampaigns() {
  const [mode, setMode] = useState<Mode>('campaigns')
  const [activeOnly, setActiveOnly] = useState(true)

  const campaigns = useQuery<CampaignResp>({
    queryKey: ['ads-campaign-stats', activeOnly],
    queryFn: async () => (await api.get(`/ads/campaign-stats?active_only=${activeOnly}`)).data,
    enabled: mode === 'campaigns',
  })
  const products = useQuery<SkuResp>({
    queryKey: ['ads-product-stats'],
    queryFn: async () => (await api.get('/ads/product-stats')).data,
    enabled: mode === 'products',
  })

  const isLoading = mode === 'campaigns' ? campaigns.isLoading : products.isLoading
  const totalSpend = mode === 'campaigns' ? campaigns.data?.total_spend : products.data?.total_spend
  const totalSales = mode === 'campaigns' ? campaigns.data?.total_orders_money : products.data?.total_sales
  const drrPct = mode === 'campaigns' ? campaigns.data?.drr_pct : products.data?.drr_pct
  const skipped = (mode === 'campaigns' ? campaigns.data?.skipped_cabinets : products.data?.skipped_cabinets) ?? []

  const tab = (m: Mode, label: string) => (
    <button
      onClick={() => setMode(m)}
      className={cn('px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
        mode === m ? 'bg-indigo-600 text-white' : 'text-fg-muted hover:bg-bg-subtle')}
    >
      {label}
    </button>
  )

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Реклама «Оплата за клик»</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            {mode === 'products' && products.data?.date ? `По товарам за ${products.data.date} · ` : 'По кампаниям · '}
            ДРР считается без расхода лимитов Ozon
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex gap-1 p-1 rounded-lg bg-bg-subtle/60">
            {tab('campaigns', 'По кампаниям')}
            {tab('products', 'По товарам')}
          </div>
          {mode === 'campaigns' && (
            <label className="flex items-center gap-2 text-sm text-fg-muted cursor-pointer">
              <input type="checkbox" checked={activeOnly}
                onChange={(e) => setActiveOnly(e.target.checked)} className="accent-indigo-600" />
              только активные
            </label>
          )}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Card className="p-4">
          <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">Расход на рекламу</p>
          <p className="text-[22px] font-semibold text-rose-700 mt-1 tabular-nums">{formatCurrency(totalSpend ?? 0)}</p>
        </Card>
        <Card className="p-4">
          <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">Продажи с рекламы</p>
          <p className="text-[22px] font-semibold text-emerald-700 mt-1 tabular-nums">{formatCurrency(totalSales ?? 0)}</p>
        </Card>
        <Card className="p-4">
          <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">ДРР (общий)</p>
          <p className="text-[22px] font-semibold text-indigo-700 mt-1 tabular-nums">{drrPct != null ? `${drrPct}%` : '—'}</p>
        </Card>
      </div>

      {mode === 'products' && products.data ? (
        <p className="text-xs text-fg-muted">
          Сматчено с товарами: {products.data.matched_to_products} из {products.data.rows.length}
        </p>
      ) : null}
      {skipped.length ? (
        <p className="text-xs text-amber-700">Пропущены кабинеты без Performance API: {skipped.join(', ')}</p>
      ) : null}

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 flex justify-center text-fg-muted"><Loader2 className="w-5 h-5 animate-spin" /></div>
        ) : mode === 'campaigns' ? (
          <CampaignTable rows={campaigns.data?.rows ?? []} />
        ) : (
          <SkuTable rows={products.data?.rows ?? []} />
        )}
      </Card>
    </div>
  )
}

function DrrCell({ drr }: { drr: number }) {
  return (
    <td className={cn('py-2.5 px-4 text-right tabular-nums font-semibold',
      drr > 15 ? 'text-rose-700' : drr > 0 ? 'text-fg' : 'text-fg-muted')}>
      {drr}%
    </td>
  )
}

function Empty() {
  return (
    <div className="py-16 flex flex-col items-center gap-2 text-fg-muted">
      <Megaphone className="w-6 h-6 opacity-40" />
      <span className="text-sm">Нет данных</span>
    </div>
  )
}

function CampaignTable({ rows }: { rows: CampaignRow[] }) {
  if (rows.length === 0) return <Empty />
  return (
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
              <DrrCell drr={r.drr} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SkuTable({ rows }: { rows: SkuRow[] }) {
  if (rows.length === 0) return <Empty />
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-bg-subtle/50 border-b border-border-subtle text-fg-muted">
          <tr>
            <th className="py-2.5 px-4 font-medium text-left">товар</th>
            <th className="py-2.5 px-4 font-medium text-left">кабинет</th>
            <th className="py-2.5 px-4 font-medium text-right">показы</th>
            <th className="py-2.5 px-4 font-medium text-right">клики</th>
            <th className="py-2.5 px-4 font-medium text-right">CTR</th>
            <th className="py-2.5 px-4 font-medium text-right">ср. клик</th>
            <th className="py-2.5 px-4 font-medium text-right">расход</th>
            <th className="py-2.5 px-4 font-medium text-right">заказы</th>
            <th className="py-2.5 px-4 font-medium text-right">продажи</th>
            <th className="py-2.5 px-4 font-medium text-right">ДРР</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.sku}-${i}`} className="border-b border-border-subtle/60 hover:bg-bg-subtle/40">
              <td className="py-2.5 px-4">
                <div className="font-medium text-fg">{r.product_name || `SKU ${r.sku}`}</div>
                <div className="text-[11px] text-fg-muted">{r.sku}{r.product_name ? '' : ' · не сматчен'}</div>
              </td>
              <td className="py-2.5 px-4 text-fg-muted">{r.cabinet_name}</td>
              <td className="py-2.5 px-4 text-right tabular-nums">{formatNumber(r.views)}</td>
              <td className="py-2.5 px-4 text-right tabular-nums">{formatNumber(r.clicks)}</td>
              <td className="py-2.5 px-4 text-right tabular-nums text-fg-muted">{r.ctr}%</td>
              <td className="py-2.5 px-4 text-right tabular-nums text-fg-muted">{formatCurrency(r.avg_cpc)}</td>
              <td className="py-2.5 px-4 text-right tabular-nums text-rose-700">{formatCurrency(r.spend)}</td>
              <td className="py-2.5 px-4 text-right tabular-nums">{formatNumber(r.orders)}</td>
              <td className="py-2.5 px-4 text-right tabular-nums text-emerald-700">{formatCurrency(r.sales)}</td>
              <DrrCell drr={r.drr} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
