/**
 * /products/competitors — официальные цены конкурентов из Ozon
 * /v5/product/info/prices.
 *
 * Что показываем per-SKU:
 * - Наша цена + min_allowed
 * - External min price (Wildberries и др. маркетплейсы)
 * - Ozon min price (другие продавцы того же товара на Ozon)
 * - color_index (RED/YELLOW/BLUE/SUPER) — официальная метка Ozon
 * - external_index = наша / рыночная (< 1 = мы дешевле)
 * - Verdict + recommendation
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Target, Loader2, ExternalLink, ShoppingBag } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { AskAIButton } from '@/components/AskAIButton'
import { api } from '@/lib/api'
import { useCabinetStore } from '@/stores/cabinet'
import { formatCurrency, cn } from '@/lib/utils'

interface Row {
  product_id: string
  offer_id: string | null
  ozon_sku: number | null
  cabinet_name: string
  our_price_rub: number | null
  marketing_seller_price_rub: number | null
  old_price_rub: number | null
  min_allowed_price_rub: number | null
  external_min_price_rub: number | null
  external_index: number | null
  ozon_min_price_rub: number | null
  ozon_index: number | null
  self_other_marketplaces_min_rub: number | null
  color_index: string | null
  verdict: string
  recommendation: string | null
}

interface Resp {
  items: Row[]
  summary: {
    total: number
    counts_by_color: Record<string, number>
    note: string
  }
}

const COLOR_STYLE: Record<string, string> = {
  RED: 'bg-rose-50 text-rose-700 border-rose-200',
  YELLOW: 'bg-amber-50 text-amber-700 border-amber-200',
  BLUE: 'bg-blue-50 text-blue-700 border-blue-200',
  SUPER: 'bg-emerald-50 text-emerald-700 border-emerald-200',
}

export function CompetitorPrices() {
  const { selectedCabinetIds } = useCabinetStore()
  const cabinetId = selectedCabinetIds[0] || null
  const [onlyProblems, setOnlyProblems] = useState(false)

  const { data, isLoading } = useQuery<Resp>({
    queryKey: ['competitor-prices', cabinetId, onlyProblems],
    queryFn: async () => {
      const p = new URLSearchParams({ only_red_yellow: String(onlyProblems) })
      if (cabinetId) p.append('cabinet_id', cabinetId)
      return (await api.get(`/competitor-prices/?${p.toString()}`)).data
    },
  })

  const items = data?.items || []
  const c = data?.summary.counts_by_color || {}

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
            <Target className="w-6 h-6 text-rose-500" />
            Конкуренты — цены
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            Минимальные цены конкурентов из Ozon /v5/product/info/prices.
            color_index — официальная метка Ozon: RED = мы дороже рынка.
          </p>
        </div>
        <AskAIButton
          context={{
            type: 'table',
            source_page: 'competitor-prices',
            source_label: 'Конкуренты — цены',
            metrics: ['external_min_price_rub', 'external_index', 'color_index', 'our_price_rub'],
            cabinet_ids: selectedCabinetIds,
          }}
          question="Какие SKU дороже рынка? Какую цену поставить?"
          variant="solid"
        />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <SumCard label="🔴 Дороже рынка" count={c.RED || 0} tone="rose" />
        <SumCard label="🟡 Близко к границе" count={c.YELLOW || 0} tone="amber" />
        <SumCard label="🔵 Конкурентоспособно" count={c.BLUE || 0} tone="blue" />
        <SumCard label="🟢 Супер-цена" count={c.SUPER || 0} tone="emerald" />
        <SumCard label="⚪ Без индекса" count={c.OTHER || 0} tone="gray" />
      </div>

      <Card className="p-3 flex items-center justify-between text-sm">
        <label className="inline-flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={onlyProblems}
            onChange={(e) => setOnlyProblems(e.target.checked)} className="rounded" />
          <span>Только 🔴/🟡 (требуют действия)</span>
        </label>
        <span className="text-xs text-fg-muted">{items.length} SKU</span>
      </Card>

      {data?.summary.note && (
        <p className="text-xs text-fg-muted px-1">{data.summary.note}</p>
      )}

      {isLoading ? (
        <div className="text-center py-6"><Loader2 className="w-5 h-5 animate-spin mx-auto text-fg-muted" /></div>
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-fg-muted bg-bg-subtle/30">
              <tr>
                <th className="py-2 px-3 text-left">SKU</th>
                <th className="py-2 px-3 text-center">Метка</th>
                <th className="py-2 px-3 text-right">Наша</th>
                <th className="py-2 px-3 text-right">Min внешн.</th>
                <th className="py-2 px-3 text-right">Min Ozon</th>
                <th className="py-2 px-3 text-right">Индекс</th>
                <th className="py-2 px-3 text-left">Совет</th>
              </tr>
            </thead>
            <tbody>
              {items.map((i) => {
                const cls = COLOR_STYLE[i.color_index || ''] || 'bg-gray-50 text-gray-700 border-gray-200'
                return (
                  <tr key={`${i.product_id}-${i.ozon_sku}`}
                      className="border-t border-border-subtle/40 hover:bg-bg-subtle/20">
                    <td className="py-2 px-3 max-w-[280px]">
                      <div className="text-fg text-xs">
                        {i.ozon_sku && (
                          <a href={`https://ozon.ru/product/${i.ozon_sku}`} target="_blank"
                             className="font-mono hover:underline">{i.ozon_sku}</a>
                        )}
                      </div>
                      <div className="text-[11px] text-fg-muted">
                        {i.offer_id} · {i.cabinet_name}
                      </div>
                    </td>
                    <td className="py-2 px-3 text-center">
                      <span className={cn('inline-flex px-2 py-0.5 rounded border text-xs font-medium', cls)}>
                        {i.color_index || '—'}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums">
                      {i.our_price_rub ? formatCurrency(i.our_price_rub) : '—'}
                      {i.old_price_rub && i.old_price_rub > (i.our_price_rub || 0) && (
                        <div className="text-[10px] text-fg-subtle line-through">
                          {formatCurrency(i.old_price_rub)}
                        </div>
                      )}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums">
                      {i.external_min_price_rub ? (
                        <span className="inline-flex items-center gap-1">
                          {formatCurrency(i.external_min_price_rub)}
                          <ShoppingBag className="w-3 h-3 text-fg-muted" />
                        </span>
                      ) : '—'}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums">
                      {i.ozon_min_price_rub ? formatCurrency(i.ozon_min_price_rub) : '—'}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums">
                      {i.external_index !== null ? (
                        <span className={cn(
                          'font-mono text-xs',
                          (i.external_index || 1) > 1.1 && 'text-rose-700',
                          (i.external_index || 1) >= 0.95 && (i.external_index || 1) <= 1.1 && 'text-amber-700',
                          (i.external_index || 1) < 0.95 && 'text-emerald-700',
                        )}>
                          {i.external_index.toFixed(2)}×
                        </span>
                      ) : '—'}
                    </td>
                    <td className="py-2 px-3 max-w-[260px]">
                      <div className="text-xs text-fg">{i.verdict}</div>
                      {i.recommendation && (
                        <div className="text-[11px] text-fg-muted mt-0.5">💡 {i.recommendation}</div>
                      )}
                    </td>
                  </tr>
                )
              })}
              {items.length === 0 && (
                <tr><td colSpan={7} className="py-6 text-center text-fg-muted">
                  {onlyProblems ? 'Все цены в норме!' : 'Нет данных от Ozon.'}
                </td></tr>
              )}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}

function SumCard({ label, count, tone }: { label: string; count: number; tone: 'rose'|'amber'|'blue'|'emerald'|'gray' }) {
  const t = { rose: 'text-rose-700', amber: 'text-amber-700',
              blue: 'text-blue-700', emerald: 'text-emerald-700', gray: 'text-gray-600' }[tone]
  return (
    <Card className="p-3">
      <div className="text-xs text-fg-muted">{label}</div>
      <div className={cn('text-2xl font-semibold mt-0.5 tabular-nums', t)}>{count}</div>
    </Card>
  )
}
