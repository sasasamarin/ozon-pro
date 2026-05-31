/**
 * Карточка «Экономика товара за 30 дней» — встраивается в /products/{id}.
 * Использует /products/economics endpoint с фильтром по product_id.
 */
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Loader2, ArrowRight, TrendingUp, Info } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'

interface EcoRow {
  product_id: string
  qty_delivered: number
  revenue: number
  avg_seller_price: number | null
  avg_customer_price: number | null
  spp_pct: number | null
  cost_per_unit: number | null
  commission_pct: number
  commission_total: number
  logistics_total: number
  acquiring_total: number
  ad_spend_total: number
  cost_total: number
  operating_profit: number
  tax_amount: number
  vat_amount: number
  net_profit: number
  net_margin_pct: number | null
  cost_missing: boolean
}
interface EcoResp {
  rows: EcoRow[]
  tax_regime_label: string
  tax_rate_pct: number
  period_from: string
  period_to: string
}

export function ProductEconomicsCard({ productId }: { productId: string }) {
  const { data, isLoading } = useQuery<EcoResp>({
    queryKey: ['products', 'economics', productId, 30],
    queryFn: async () =>
      (await api.get(`/products/economics/?days=30&product_id=${productId}`)).data,
    staleTime: 60_000,
  })

  if (isLoading) {
    return (
      <Card className="p-5 flex justify-center text-fg-muted">
        <Loader2 className="w-5 h-5 animate-spin" />
      </Card>
    )
  }
  const r = data?.rows[0]
  if (!r) {
    return (
      <Card className="p-5 text-sm text-fg-muted">
        За последние 30 дней нет доставленных продаж этого товара — экономика не рассчитана.
      </Card>
    )
  }

  return (
    <Card className="overflow-hidden">
      <div className="px-6 py-4 border-b border-border-subtle flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-base font-semibold text-fg flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-emerald-600" />
            Экономика за 30 дней
          </h2>
          <p className="text-xs text-fg-muted mt-0.5">
            Реальная P&amp;L товара с учётом налога ({data!.tax_regime_label} {data!.tax_rate_pct}%)
          </p>
        </div>
        <Link to="/products/economics"
              className="text-xs text-blue-700 hover:underline inline-flex items-center gap-1">
          Все товары <ArrowRight className="w-3 h-3" />
        </Link>
      </div>

      <div className="p-5 grid grid-cols-2 md:grid-cols-5 gap-3">
        <Mini label="Доставлено" value={`${formatNumber(r.qty_delivered)} шт`}
              hint="Единицы со status=delivered за 30 дней" />
        <Mini label="Выручка"
              value={formatCurrency(r.revenue)}
              hint="SUM(oi.price × qty) — что Ozon начислил тебе"
              tone="pos" />
        <Mini label="Цена покупателя"
              value={r.avg_customer_price != null ? formatCurrency(r.avg_customer_price) : '—'}
              hint={r.spp_pct != null ? `На ${r.spp_pct}% ниже твоей. Драйвер спроса, на выручку не влияет.` : 'Цена с СПП/Ozon-Картой'}
              tone="info"
              subValue={r.spp_pct != null ? `СПП −${r.spp_pct}%` : undefined} />
        <Mini label="Опер. прибыль"
              value={formatCurrency(r.operating_profit)}
              hint="Выручка − себест − комиссия − логистика − эквайринг − реклама. ДО налога."
              tone={r.operating_profit >= 0 ? 'pos' : 'neg'} />
        <Mini label="Чистая прибыль"
              value={formatCurrency(r.net_profit)}
              hint={`После налога ${data!.tax_regime_label} ${data!.tax_rate_pct}%. Это сколько ОСТАЛОСЬ.`}
              tone={r.net_profit >= 0 ? 'pos' : 'neg'}
              big
              subValue={r.net_margin_pct != null ? `маржа ${r.net_margin_pct.toFixed(1)}%` : undefined} />
      </div>

      {/* Декомпозиция расходов */}
      <div className="px-5 pb-5">
        <div className="text-[10px] text-fg-muted uppercase tracking-wider mb-2">
          Куда уходит выручка
        </div>
        <table className="w-full text-xs">
          <tbody>
            <Row label="Выручка" amount={r.revenue} tone="pos" />
            {r.cost_total > 0 && <Row label="Себестоимость" amount={-r.cost_total} />}
            {r.cost_missing && (
              <tr><td colSpan={3} className="text-amber-700 text-[11px] py-1">
                ⚠ Себестоимость не заполнена — прибыль завышена. Заполни в карточке справа.
              </td></tr>
            )}
            <Row label={`Комиссия Ozon (${r.commission_pct}%)`} amount={-r.commission_total} />
            <Row label="Логистика" amount={-r.logistics_total} />
            <Row label="Эквайринг" amount={-r.acquiring_total} />
            {r.ad_spend_total > 0 && <Row label="Реклама" amount={-r.ad_spend_total} />}
            <Row label="ОПЕР. ПРИБЫЛЬ" amount={r.operating_profit} bold />
            {r.vat_amount > 0 && <Row label="НДС" amount={-r.vat_amount} />}
            <Row label={`Налог ${data!.tax_regime_label} ${data!.tax_rate_pct}%`} amount={-r.tax_amount} />
            <Row label="ЧИСТАЯ ПРИБЫЛЬ" amount={r.net_profit} bold accent />
          </tbody>
        </table>

        <div className="mt-3 flex items-start gap-2 text-[11px] text-fg-muted">
          <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          <span>
            Цена продавца {r.avg_seller_price != null ? formatCurrency(r.avg_seller_price) : '—'} —
            от неё считается выручка. Себестоимость
            {r.cost_per_unit != null ? ` ${formatCurrency(r.cost_per_unit)} за шт` : ' не указана'}.
          </span>
        </div>
      </div>
    </Card>
  )
}

function Mini({ label, value, hint, tone = 'neu', big = false, subValue }: {
  label: string; value: string; hint: string
  tone?: 'pos' | 'neg' | 'info' | 'neu'; big?: boolean; subValue?: string
}) {
  const c = tone === 'pos' ? 'text-emerald-700'
          : tone === 'neg' ? 'text-rose-700'
          : tone === 'info' ? 'text-blue-700'
          : 'text-fg'
  return (
    <div className={cn('rounded-md border border-border-subtle bg-bg p-3', big && 'border-emerald-200')} title={hint}>
      <div className="text-[10px] text-fg-muted uppercase tracking-wider">{label}</div>
      <div className={cn('font-bold tabular-nums mt-1', big ? 'text-xl' : 'text-base', c)}>{value}</div>
      {subValue && <div className="text-[10px] text-fg-subtle">{subValue}</div>}
    </div>
  )
}

function Row({ label, amount, bold = false, accent = false, tone }: {
  label: string; amount: number; bold?: boolean; accent?: boolean; tone?: 'pos'
}) {
  const c = accent ? (amount >= 0 ? 'text-emerald-700' : 'text-rose-700')
          : tone === 'pos' ? 'text-emerald-700'
          : amount < 0 ? 'text-rose-700' : 'text-fg'
  return (
    <tr className={cn('border-b border-border-subtle/40', bold && 'border-t-2 border-border-subtle')}>
      <td className={cn('py-1.5 pr-4', bold && 'font-semibold')}>{label}</td>
      <td className={cn('py-1.5 text-right tabular-nums', c, bold && 'font-bold')}>
        {amount > 0 ? '+' : ''}{formatCurrency(amount)}
      </td>
    </tr>
  )
}
