/**
 * «Экономика продаж» — единая P&L-таблица по товарам.
 *
 * Колонки: товар / кабинет / qty / выручка / комиссия / себест / реклама / лог / эквайринг /
 *           опер. прибыль / налог / чистая прибыль / маржа %
 * Период: 7/28/30/90/365 дней
 * Баннер про незаполненную себестоимость (как у nepsell).
 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Loader2, AlertTriangle, Info, TrendingUp, TrendingDown, FileSpreadsheet, Pencil } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { SelectedProductBanner } from '@/components/SelectedProductBanner'
import { SourceBadge, SourceLegend } from '@/components/SourceBadge'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'
import { useProductFilter } from '@/stores/product_filter'
import { useCategoryFilter } from '@/stores/category_filter'
import { useTagFilter } from '@/stores/tag_filter'
import { DateRangeBar } from '@/components/DateRangeBar'
import { addDateParams } from '@/lib/dateParams'

interface EcoRow {
  product_id: string
  product_name: string
  offer_id: string
  ozon_sku: number
  cabinet_name: string
  is_archived: boolean
  // Источник каждого поля: 'api' / 'xlsx' / 'estimated' / 'manual' / 'missing'
  sources: Record<string, string>
  qty_delivered: number
  revenue: number
  returned_revenue: number
  effective_revenue: number
  spp_points: number
  partner_programs: number
  avg_seller_price: number | null
  avg_customer_price: number | null
  avg_customer_price_estimate?: number | null
  spp_pct: number | null
  cost_per_unit: number | null
  commission_pct: number
  commission_per_unit: number
  logistics_per_unit: number
  acquiring_per_unit: number
  ad_spend_per_unit: number
  cost_total: number
  commission_total: number
  logistics_total: number
  last_mile_total: number
  storage_total: number
  posting_handling_total: number
  acquiring_total: number
  return_handling_total: number
  reverse_logistics_total: number
  disposal_total: number
  ovh_extra_total: number
  operational_errors_total: number
  ad_cpc_total: number
  ad_cpo_total: number
  ad_star_total: number
  ad_paid_brand_total: number
  ad_reviews_total: number
  ad_spend_total: number
  operating_profit: number
  operating_margin_pct: number | null
  tax_amount: number
  vat_amount: number
  net_profit: number
  net_margin_pct: number | null
  cost_missing: boolean
  ozon_profit: number | null
  ozon_profit_diff: number | null
}

interface EcoTotals {
  qty_delivered: number
  revenue: number
  returned_revenue: number
  effective_revenue: number
  cost_total: number
  commission_total: number
  logistics_total: number
  acquiring_total: number
  ad_spend_total: number
  storage_total: number
  operating_profit: number
  tax_amount: number
  vat_amount: number
  net_profit: number
  net_margin_pct: number | null
  products_total: number
  products_with_cost: number
  products_missing_cost: number
  products_with_xlsx: number
  products_estimated: number
}

interface EcoResp {
  period_from: string
  period_to: string
  tax_regime: string
  tax_regime_label: string
  tax_rate_pct: number
  months_with_xlsx: string[]
  xlsx_coverage_pct: number
  rows: EcoRow[]
  totals: EcoTotals
}

const PERIODS = [
  { d: 7, label: '7 дней' },
  { d: 28, label: '28 дней' },
  { d: 30, label: '30 дней' },
  { d: 90, label: '90 дней' },
  { d: 365, label: 'Год' },
]

type SortBy = 'revenue' | 'net_profit' | 'net_margin' | 'qty' | 'op_profit' | 'tax'

export function ProductEconomics() {
  const { selectedCabinetIds } = useCabinetStore()
  const { selectedProductId } = useProductFilter()
  const { selectedCategoryId } = useCategoryFilter()
  const { selectedTags } = useTagFilter()
  const [days, setDays] = useState(30)
  const [dateFrom, setDateFrom] = useState<string | null>(null)
  const [dateTo, setDateTo] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState<SortBy>('revenue')
  const [showArchived, setShowArchived] = useState(false)
  const [search, setSearch] = useState('')

  const { data, isLoading } = useQuery<EcoResp>({
    queryKey: ['products', 'economics', days, dateFrom, dateTo, selectedCabinetIds, showArchived, selectedProductId, selectedCategoryId, selectedTags],
    queryFn: async () => {
      const p = new URLSearchParams()
      addDateParams(p, days, dateFrom, dateTo)
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      if (showArchived) p.append('include_archived', 'true')
      if (selectedProductId) p.append('product_id', selectedProductId)
      if (selectedCategoryId != null) p.append('category_id', String(selectedCategoryId))
      selectedTags.forEach((t) => p.append('tags', t))
      return (await api.get(`/products/economics/?${p.toString()}`, { timeout: 60_000 })).data
    },
  })

  const sortedRows = useMemo(() => {
    if (!data) return []
    const filtered = search
      ? data.rows.filter((r) =>
          r.product_name.toLowerCase().includes(search.toLowerCase()) ||
          r.offer_id.toLowerCase().includes(search.toLowerCase()) ||
          String(r.ozon_sku).includes(search)
        )
      : data.rows
    const keyFn = {
      revenue:    (r: EcoRow) => r.revenue,
      net_profit: (r: EcoRow) => r.net_profit,
      net_margin: (r: EcoRow) => r.net_margin_pct ?? -Infinity,
      qty:        (r: EcoRow) => r.qty_delivered,
      op_profit:  (r: EcoRow) => r.operating_profit,
      tax:        (r: EcoRow) => r.tax_amount,
    }[sortBy]
    return [...filtered].sort((a, b) => keyFn(b) - keyFn(a))
  }, [data, sortBy, search])

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Экономика продаж</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Полный P&amp;L по каждому товару: выручка → все вычеты → налог → чистая прибыль.
            {data && (
                <span className="ml-2 text-xs">
                · Налог: <strong>{data.tax_regime_label} {data.tax_rate_pct}%</strong>{' '}
                  <Link to="/settings" className="text-blue-700 hover:underline">сменить</Link>
              </span>
            )}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <DateRangeBar
              days={days}
              onChange={(r) => {
                setDays(r.days);
                setDateFrom(r.dateFrom);
                setDateTo(r.dateTo)
              }}
          />
        </div>
      </div>

      <SelectedProductBanner supported/>

      {/* Баннер «не заполнена себестоимость» — критично для корректности */}
      {data && data.totals.products_missing_cost > 0 && (
          <Card className="p-4 flex items-start gap-3 bg-rose-50/60 border-rose-200/60">
          <AlertTriangle className="w-5 h-5 text-rose-700 mt-0.5 shrink-0" />
          <div className="text-sm text-rose-900 flex-1">
            <strong>Прибыль ЗАВЫШЕНА:</strong> у {data.totals.products_missing_cost} из {data.totals.products_total} товаров
            не заполнена себестоимость → COGS = 0 → прибыль выглядит больше реальной на десятки процентов.{' '}
            <Link to="/products?missing_cost=1&arch=all" className="font-medium underline">
              Заполнить ({data.totals.products_missing_cost} товаров) →
            </Link>
          </div>
        </Card>
      )}

      {/* Баннер покрытия XLSX «Экономика магазина» */}
      {data && (
        <Card className={cn(
          'p-3 flex items-center gap-3 text-sm',
          data.totals.products_with_xlsx > 0
            ? 'bg-blue-50/60 border-blue-200/60'
            : 'bg-amber-50/60 border-amber-200/60',
        )}>
          <FileSpreadsheet className={cn(
            'w-5 h-5 shrink-0',
            data.totals.products_with_xlsx > 0 ? 'text-blue-700' : 'text-amber-700',
          )} />
          <div className="flex-1 flex items-center justify-between flex-wrap gap-2">
            <div>
              {data.totals.products_with_xlsx > 0 ? (
                <>
                  <strong className="text-blue-900">
                    {data.totals.products_with_xlsx} из {data.totals.products_total} товаров
                  </strong>
                  {' '}({data.xlsx_coverage_pct}%) — точные числа из XLSX Ozon (хранение,
                  реклама детально, доплаты СПП). Месяцы: {data.months_with_xlsx.join(', ') || '—'}.
                </>
              ) : (
                <>
                  <strong className="text-amber-900">XLSX «Экономика магазина» за этот период не загружен.</strong>{' '}
                  Хранение и детальная реклама будут = 0, остальные расходы — оценка.
                </>
              )}
            </div>
            <Link to="/finance/unit-economy/import"
                  className="text-xs font-medium px-3 py-1.5 rounded-md bg-fg text-bg hover:opacity-90 inline-flex items-center gap-1.5">
              <FileSpreadsheet className="w-3.5 h-3.5" />
              Загрузить XLSX
            </Link>
          </div>
        </Card>
      )}

      {/* Легенда источников */}
      {data && data.rows.length > 0 && (
        <div className="px-1">
          <SourceLegend />
        </div>
      )}

      {/* Сводка KPI */}
      {data && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <KpiBox label="Выручка" value={formatCurrency(data.totals.revenue)}
                  hint="Сумма oi.price × qty доставленных за период" />
          <KpiBox label="Опер. прибыль"
                  value={formatCurrency(data.totals.operating_profit)}
                  hint="Выручка − себест − комиссия Ozon − логистика − эквайринг − реклама. ДО налога."
                  tone={data.totals.operating_profit >= 0 ? 'pos' : 'neg'} />
          <KpiBox label={`Налог (${data.tax_regime_label})`}
                  value={formatCurrency(data.totals.tax_amount + data.totals.vat_amount)}
                  hint={`По компании-режиму ${data.tax_regime_label} ${data.tax_rate_pct}%. ${data.totals.vat_amount > 0 ? `Включая НДС ${formatCurrency(data.totals.vat_amount)}.` : ''}`}
                  tone="neg" />
          <KpiBox label="Чистая прибыль"
                  value={formatCurrency(data.totals.net_profit)}
                  hint="После всех вычетов И налога. Это сколько у тебя реально осталось."
                  tone={data.totals.net_profit >= 0 ? 'pos' : 'neg'}
                  big />
          <KpiBox label="Чистая маржа"
                  value={data.totals.net_margin_pct != null ? `${data.totals.net_margin_pct.toFixed(1)}%` : '—'}
                  hint="net_profit / revenue × 100. Идеал >15%."
                  tone={(data.totals.net_margin_pct ?? 0) >= 15 ? 'pos' : (data.totals.net_margin_pct ?? 0) >= 5 ? 'neu' : 'neg'} />
        </div>
      )}

      {/* Тулбар таблицы */}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <input
          type="search"
          placeholder="Поиск по имени / offer_id / sku…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="px-3 py-1.5 rounded-md border border-border-subtle bg-bg w-72"
        />
        <span className="text-fg-muted text-xs">Сортировка:</span>
        {[
          ['revenue', 'выручка'],
          ['net_profit', 'чистая прибыль'],
          ['net_margin', 'маржа %'],
          ['qty', 'qty'],
        ].map(([k, l]) => (
          <button key={k} onClick={() => setSortBy(k as SortBy)} className={cn(
            'px-2 py-1 rounded text-xs',
            sortBy === k ? 'bg-fg text-bg' : 'bg-bg-subtle text-fg-muted hover:text-fg',
          )}>{l}</button>
        ))}
        <label className="flex items-center gap-1.5 text-xs text-fg-muted ml-auto">
          <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
          Показать архивные
        </label>
      </div>

      {/* Таблица */}
      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 flex justify-center text-fg-muted">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : sortedRows.length === 0 ? (
          <div className="py-12 text-center text-fg-muted text-sm">
            Нет товаров с доставленными продажами за период.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                <tr className="text-fg-muted uppercase">
                  <th className="text-left py-2 px-3">Товар / кабинет</th>
                  <th className="text-right py-2 px-2" title="Доставленные единицы за период">qty</th>
                  <th className="text-right py-2 px-2" title="Средняя цена продавца за единицу (от чего считаем выручку)">Цена прод.</th>
                  <th className="text-right py-2 px-2" title="Средняя цена покупателя с СПП — что физически платил клиент">Цена пок.</th>
                  <th className="text-right py-2 px-2" title="Выручка = sum(oi.price × qty)">Выручка</th>
                  <th className="text-right py-2 px-2" title="Себестоимость закупки × qty">Себест.</th>
                  <th className="text-right py-2 px-2" title="Реальная комиссия Ozon из products.sales_percent_fbo">Комис.</th>
                  <th className="text-right py-2 px-2" title="Доставка до клиента + last-mile ≈ 306₽/qty">Логист.</th>
                  <th className="text-right py-2 px-2" title="1.5% от выручки">Эквайр.</th>
                  <th className="text-right py-2 px-2" title="Расход на рекламу из AdStatistics">Реклама</th>
                  <th className="text-right py-2 px-2 font-semibold" title="Выручка − все вычеты. ДО налога.">Опер. приб.</th>
                  <th className="text-right py-2 px-2" title="Налог компании">Налог</th>
                  <th className="text-right py-2 px-2 font-semibold bg-emerald-50/30" title="ПОСЛЕ налога — реально твои">Чистая</th>
                  <th className="text-right py-2 px-2" title="Чистая / Выручка × 100">Маржа</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {sortedRows.map((r) => (
                  <tr key={r.product_id} className={cn('hover:bg-bg-subtle/40', r.is_archived && 'opacity-60')}>
                    <td className="py-2 px-3">
                      <Link to={`/products/${r.product_id}`}
                            className="font-medium text-fg hover:text-blue-700 truncate block max-w-[280px]"
                            title={r.product_name}>
                        {r.product_name}
                      </Link>
                      <div className="text-[10px] text-fg-subtle font-mono">
                        {r.offer_id} · {r.cabinet_name}
                        {r.cost_missing && (
                          <span className="ml-2 text-amber-700">⚠ без себест.</span>
                        )}
                      </div>
                    </td>
                    <td className="text-right py-2 px-2 tabular-nums">{formatNumber(r.qty_delivered)}</td>
                    <td className="text-right py-2 px-2 tabular-nums">
                      {r.avg_seller_price != null ? formatNumber(Math.round(r.avg_seller_price)) : '—'}
                    </td>
                    <td className="text-right py-2 px-2 tabular-nums text-blue-700">
                      {r.avg_customer_price != null ? (
                        <>
                          {formatNumber(Math.round(r.avg_customer_price))}
                          {r.spp_pct != null && (
                            <div className="text-[10px] text-blue-500">−{r.spp_pct}%</div>
                          )}
                        </>
                      ) : r.avg_customer_price_estimate != null ? (
                        <span
                          className="text-fg-muted italic"
                          title="Точных данных за этот период нет (Ozon API >90 дней). Это средняя за месяц из отчёта о реализации."
                        >
                          ≈ {formatNumber(Math.round(r.avg_customer_price_estimate))}
                          <div className="text-[10px] text-fg-muted">оценка</div>
                        </span>
                      ) : '—'}
                    </td>
                    <td className="text-right py-2 px-2 tabular-nums font-medium text-emerald-700">
                      <span className="inline-flex items-center gap-1">
                        {formatCurrency(r.revenue)}
                        <SourceBadge source={r.sources?.revenue} />
                      </span>
                      {r.storage_total > 0 && (
                        <div className="text-[10px] text-rose-600">
                          в т.ч. −{formatCurrency(r.storage_total)} хранение
                        </div>
                      )}
                    </td>
                    <td className="text-right py-2 px-2 tabular-nums text-rose-700">
                      <span className="inline-flex items-center gap-1">
                        {r.cost_total > 0 ? `−${formatCurrency(r.cost_total)}` : '—'}
                        <SourceBadge source={r.cost_missing ? 'missing' : 'manual'} />
                      </span>
                    </td>
                    <td className="text-right py-2 px-2 tabular-nums text-rose-700">
                      <span className="inline-flex items-center gap-1">
                        −{formatCurrency(r.commission_total)}
                        <SourceBadge source={r.sources?.commission_total} />
                      </span>
                      <div className="text-[10px] text-fg-subtle">{r.commission_pct}%</div>
                    </td>
                    <td className="text-right py-2 px-2 tabular-nums text-rose-700">
                      <span className="inline-flex items-center gap-1">
                        −{formatCurrency(r.logistics_total)}
                        <SourceBadge source={r.sources?.logistics_total} />
                      </span>
                    </td>
                    <td className="text-right py-2 px-2 tabular-nums text-rose-700">
                      <span className="inline-flex items-center gap-1">
                        −{formatCurrency(r.acquiring_total)}
                        <SourceBadge source={r.sources?.acquiring_total} />
                      </span>
                    </td>
                    <td className="text-right py-2 px-2 tabular-nums text-rose-700">
                      <span className="inline-flex items-center gap-1">
                        {r.ad_spend_total > 0 ? `−${formatCurrency(r.ad_spend_total)}` : '—'}
                        <SourceBadge source={r.sources?.ad_spend_total} />
                      </span>
                    </td>
                    <td className={cn('text-right py-2 px-2 tabular-nums font-semibold',
                      r.operating_profit >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
                      {formatCurrency(r.operating_profit)}
                    </td>
                    <td className="text-right py-2 px-2 tabular-nums text-rose-700">
                      −{formatCurrency(r.tax_amount + r.vat_amount)}
                    </td>
                    <td className={cn('text-right py-2 px-2 tabular-nums font-bold bg-emerald-50/30',
                      r.net_profit >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
                      {formatCurrency(r.net_profit)}
                    </td>
                    <td className={cn('text-right py-2 px-2 tabular-nums font-semibold',
                      (r.net_margin_pct ?? 0) >= 15 ? 'text-emerald-700' :
                      (r.net_margin_pct ?? 0) >= 5 ? 'text-amber-700' : 'text-rose-700')}>
                      {r.net_margin_pct != null ? `${r.net_margin_pct.toFixed(1)}%` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
              {data && (
                <tfoot className="bg-bg-subtle/60 border-t-2 border-border-subtle">
                  <tr className="text-xs font-semibold text-fg">
                    <td className="py-2.5 px-3">
                      Итого · {data.totals.products_total} товаров
                      <div className="text-[10px] text-fg-subtle font-normal">
                        период: {data.period_from} → {data.period_to}
                      </div>
                    </td>
                    <td className="text-right py-2.5 px-2 tabular-nums">{formatNumber(data.totals.qty_delivered)}</td>
                    <td colSpan={2}></td>
                    <td className="text-right py-2.5 px-2 tabular-nums text-emerald-700">{formatCurrency(data.totals.revenue)}</td>
                    <td className="text-right py-2.5 px-2 tabular-nums text-rose-700">
                      {data.totals.cost_total > 0 ? `−${formatCurrency(data.totals.cost_total)}` : '—'}
                    </td>
                    <td className="text-right py-2.5 px-2 tabular-nums text-rose-700">−{formatCurrency(data.totals.commission_total)}</td>
                    <td className="text-right py-2.5 px-2 tabular-nums text-rose-700">−{formatCurrency(data.totals.logistics_total)}</td>
                    <td className="text-right py-2.5 px-2 tabular-nums text-rose-700">−{formatCurrency(data.totals.acquiring_total)}</td>
                    <td className="text-right py-2.5 px-2 tabular-nums text-rose-700">
                      {data.totals.ad_spend_total > 0 ? `−${formatCurrency(data.totals.ad_spend_total)}` : '—'}
                    </td>
                    <td className={cn('text-right py-2.5 px-2 tabular-nums',
                      data.totals.operating_profit >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
                      {formatCurrency(data.totals.operating_profit)}
                    </td>
                    <td className="text-right py-2.5 px-2 tabular-nums text-rose-700">
                      −{formatCurrency(data.totals.tax_amount + data.totals.vat_amount)}
                    </td>
                    <td className={cn('text-right py-2.5 px-2 tabular-nums bg-emerald-100/40 font-bold',
                      data.totals.net_profit >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
                      {formatCurrency(data.totals.net_profit)}
                    </td>
                    <td className={cn('text-right py-2.5 px-2 tabular-nums',
                      (data.totals.net_margin_pct ?? 0) >= 15 ? 'text-emerald-700' :
                      (data.totals.net_margin_pct ?? 0) >= 5 ? 'text-amber-700' : 'text-rose-700')}>
                      {data.totals.net_margin_pct != null ? `${data.totals.net_margin_pct.toFixed(1)}%` : '—'}
                    </td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        )}
      </Card>

      {/* Объяснение */}
      <Card className="p-4 bg-blue-50/60 border-blue-200/60 text-sm text-blue-900/90">
        <div className="flex items-start gap-2">
          <Info className="w-4 h-4 text-blue-700 mt-0.5 shrink-0" />
          <div className="space-y-1">
            <div><strong>Как считается чистая прибыль:</strong></div>
            <div className="font-mono text-[11px] bg-bg/60 rounded p-2 leading-relaxed">
              выручка (oi.price × qty доставлены)<br/>
              − себестоимость (cost_price × qty)<br/>
              − комиссия Ozon (sales_percent_fbo × выручка)<br/>
              − логистика (~306₽ × qty)<br/>
              − эквайринг (1.5% × выручка)<br/>
              − расход на рекламу (AdStatistics.spend)<br/>
              = ОПЕРАЦИОННАЯ ПРИБЫЛЬ<br/>
              − налог (по компании-режиму) − НДС<br/>
              = ЧИСТАЯ ПРИБЫЛЬ
            </div>
            <div className="text-xs">
              Цены в таблице: <strong>Цена продавца</strong> = что Ozon начисляет тебе (от неё считается выручка и комиссия).{' '}
              <strong>Цена покупателя</strong> = что физически платил клиент с СПП/Ozon-Картой (драйвер спроса, на твою выручку не влияет).
            </div>
          </div>
        </div>
      </Card>
    </div>
  )
}

function KpiBox({ label, value, hint, tone = 'neu', big = false }: {
  label: string
  value: string
  hint: string
  tone?: 'pos' | 'neg' | 'neu'
  big?: boolean
}) {
  const valueColor = tone === 'pos' ? 'text-emerald-700' : tone === 'neg' ? 'text-rose-700' : 'text-fg'
  return (
    <Card className={cn('p-4', big && 'border-emerald-200')} title={hint}>
      <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">{label}</p>
      <p className={cn('font-semibold mt-1 tabular-nums', big ? 'text-2xl' : 'text-xl', valueColor)}>
        {value}
      </p>
    </Card>
  )
}
