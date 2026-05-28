import { Fragment, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Package,
  AlertCircle,
  Image as ImageIcon,
  Store,
  ChevronRight,
  Warehouse,
  Loader2,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { HelpHint } from '@/components/ui/HelpHint'
import { api } from '@/lib/api'
import { formatCurrency, cn } from '@/lib/utils'
import { getErrorMessage } from '@/lib/errors'
import { useCabinetStore } from '@/stores/cabinet'

interface ProductItem {
  id: string
  name: string
  offer_id: string
  ozon_sku: number
  current_price: number | null
  old_price: number | null
  marketing_price: number | null
  min_price: number | null
  price_index: string | null
  is_archived: boolean
  image_url: string | null
  cabinet_id: string
  cabinet_name: string
  cabinet_premium_tier: string
  total_stock: number
}

interface StockRow {
  warehouse_type: string
  warehouse_name: string | null
  warehouse_id: number | null
  cluster: string | null
  free_to_sell: number
  reserved: number
  in_transit: number
  snapshot_at: string
}

type StockFilter = 'all' | 'in_stock' | 'out_of_stock'

const PRICE_INDEX_LABEL: Record<string, { label: string; tone: 'good' | 'neutral' | 'bad' }> = {
  PROFIT: { label: 'Выгодно', tone: 'good' },
  AVG_PROFIT: { label: 'Средне', tone: 'neutral' },
  NON_PROFIT: { label: 'Невыгодно', tone: 'bad' },
  WITHOUT_INDEX: { label: 'Без индекса', tone: 'neutral' },
}

function PriceIndexBadge({ value }: { value: string | null }) {
  if (!value) return null
  const meta = PRICE_INDEX_LABEL[value] || { label: value, tone: 'neutral' as const }
  return (
    <span
      className={cn(
        'text-[10px] font-medium px-1.5 py-0.5 rounded',
        meta.tone === 'good' && 'text-success bg-green-50',
        meta.tone === 'bad' && 'text-error bg-red-50',
        meta.tone === 'neutral' && 'text-fg-muted bg-bg-subtle',
      )}
    >
      {meta.label}
    </span>
  )
}

function StockBadge({ value }: { value: number }) {
  if (value === 0) {
    return <span className="text-error font-mono tabular-nums">0</span>
  }
  return <span className="text-fg font-mono tabular-nums">{value.toLocaleString('ru-RU')}</span>
}

function StockBreakdown({ productId }: { productId: string }) {
  const { data, isLoading, error } = useQuery<StockRow[]>({
    queryKey: ['product-stocks', productId],
    queryFn: async () => {
      const res = await api.get(`/products/${productId}/stocks`)
      return res.data
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-xs text-fg-muted py-2">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        Загружаем остатки по складам…
      </div>
    )
  }
  if (error) {
    return <div className="text-xs text-error py-2">{getErrorMessage(error)}</div>
  }
  if (!data || data.length === 0) {
    return <div className="text-xs text-fg-muted py-2">Снимков остатков ещё нет.</div>
  }

  // Группируем по warehouse_type для подытогов
  const grouped: Record<string, StockRow[]> = {}
  for (const row of data) {
    const k = row.warehouse_type || '—'
    if (!grouped[k]) grouped[k] = []
    grouped[k].push(row)
  }

  return (
    <div className="space-y-3 pt-1">
      {Object.entries(grouped).map(([wtype, rows]) => {
        const totals = rows.reduce(
          (acc, r) => ({
            free: acc.free + r.free_to_sell,
            reserved: acc.reserved + r.reserved,
            transit: acc.transit + r.in_transit,
          }),
          { free: 0, reserved: 0, transit: 0 },
        )
        return (
          <div key={wtype} className="border border-border-subtle rounded-md overflow-hidden">
            <div className="bg-bg-subtle/60 px-3 py-1.5 flex items-center justify-between text-[11px]">
              <span className="font-semibold uppercase tracking-wider text-fg">{wtype}</span>
              <span className="text-fg-muted">
                Доступно: <span className="font-mono text-fg">{totals.free}</span> · Резерв:{' '}
                <span className="font-mono">{totals.reserved}</span> · В пути:{' '}
                <span className="font-mono">{totals.transit}</span>
              </span>
            </div>
            <table className="w-full text-xs">
              <thead className="text-fg-subtle text-[10px] uppercase tracking-wider">
                <tr>
                  <th className="text-left py-1.5 px-3">Склад</th>
                  <th className="text-right py-1.5 px-3">Доступно</th>
                  <th className="text-right py-1.5 px-3">Резерв</th>
                  <th className="text-right py-1.5 px-3">В пути</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td className="py-1.5 px-3 text-fg-muted">
                      {r.warehouse_name || r.cluster || (
                        <span className="italic">— (всего по типу)</span>
                      )}
                    </td>
                    <td className="py-1.5 px-3 text-right font-mono">{r.free_to_sell}</td>
                    <td className="py-1.5 px-3 text-right font-mono">{r.reserved}</td>
                    <td className="py-1.5 px-3 text-right font-mono">{r.in_transit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      })}
      <div className="text-[10px] text-fg-subtle pt-1">
        <AlertCircle className="w-3 h-3 inline mr-1 -mt-0.5" />
        Снимок:{' '}
        {new Date(data[0].snapshot_at).toLocaleString('ru-RU', {
          dateStyle: 'short',
          timeStyle: 'short',
        })}{' '}
        · Полная разбивка по складам кластера — следующая задача (нужен endpoint
        /v2/analytics/stock_on_warehouses).
      </div>
    </div>
  )
}

export function Products() {
  const { selectedCabinetIds } = useCabinetStore()
  const [stockFilter, setStockFilter] = useState<StockFilter>('all')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const { data, isLoading, error } = useQuery<ProductItem[]>({
    queryKey: ['products', selectedCabinetIds],
    queryFn: async () => {
      const params = new URLSearchParams()
      selectedCabinetIds.forEach((id) => params.append('cabinet_ids', id))
      const qs = params.toString()
      const res = await api.get(qs ? `/products/?${qs}` : '/products/')
      return res.data
    },
    refetchOnMount: 'always',
    staleTime: 0,
  })

  const allProducts = data || []
  const products =
    stockFilter === 'in_stock'
      ? allProducts.filter((p) => p.total_stock > 0)
      : stockFilter === 'out_of_stock'
        ? allProducts.filter((p) => p.total_stock === 0)
        : allProducts

  const inStockCount = allProducts.filter((p) => p.total_stock > 0).length
  const outStockCount = allProducts.length - inStockCount

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-3xl font-semibold text-fg tracking-tight">Товары</h1>
            <HelpHint text="Все товары из подключенных кабинетов Ozon. Список фильтруется multi-select переключателем кабинетов в шапке. Клик по строке → разбивка остатков по типам складов (FBO/FBS). Цены — текущая+старая, остаток — суммарный по всем складам из последнего снимка." />
          </div>
          <p className="text-sm text-fg-muted mt-1.5">
            {isLoading
              ? 'Загрузка…'
              : allProducts.length === 0
                ? 'Товары не подгружены'
                : `Всего товаров: ${allProducts.length}${selectedCabinetIds.length > 0 ? ' (фильтр по выбранным кабинетам)' : ''}`}
          </p>
        </div>
        <Link to="/cabinets">
          <Button variant="secondary">
            <Store className="w-4 h-4" />К кабинетам
          </Button>
        </Link>
      </div>

      {/* Stock filter tabs */}
      {allProducts.length > 0 && (
        <div className="inline-flex rounded-lg border border-border-subtle bg-bg p-0.5 self-start">
          {([
            ['all', `Все (${allProducts.length})`],
            ['in_stock', `В наличии (${inStockCount})`],
            ['out_of_stock', `Без остатка (${outStockCount})`],
          ] as const).map(([k, label]) => (
            <button
              key={k}
              type="button"
              onClick={() => setStockFilter(k)}
              className={cn(
                'px-3 py-1.5 text-xs font-medium rounded-md transition-all',
                stockFilter === k
                  ? 'bg-bg-subtle text-fg shadow-sm'
                  : 'text-fg-muted hover:text-fg',
              )}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {error && (
        <div className="text-sm text-error bg-red-50 border border-red-200 rounded-md px-3 py-2">
          {getErrorMessage(error)}
        </div>
      )}

      {isLoading ? (
        <Card className="p-12 flex items-center justify-center text-fg-muted">
          Загрузка товаров…
        </Card>
      ) : allProducts.length === 0 ? (
        <Card className="p-12 flex flex-col items-center text-center">
          <div className="w-14 h-14 rounded-full bg-bg-subtle flex items-center justify-center mb-4">
            <Package className="w-6 h-6 text-fg-muted" />
          </div>
          <h3 className="text-lg font-semibold text-fg">Товаров пока нет</h3>
          <p className="text-sm text-fg-muted mt-1.5 max-w-md">
            Подключи кабинет Ozon — синхронизация подтянет товары автоматически.
          </p>
          <Link to="/cabinets" className="mt-6">
            <Button variant="secondary">
              <Store className="w-4 h-4" />
              К кабинетам
            </Button>
          </Link>
        </Card>
      ) : products.length === 0 ? (
        <Card className="p-12 flex flex-col items-center text-center">
          <Warehouse className="w-8 h-8 text-fg-subtle mb-3" />
          <h3 className="text-base font-semibold text-fg">
            Ничего по фильтру «{stockFilter === 'in_stock' ? 'В наличии' : 'Без остатка'}»
          </h3>
        </Card>
      ) : (
        <Card className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle/60 border-b border-border-subtle">
                <tr className="text-left text-[11px] font-semibold uppercase tracking-wider text-fg-subtle">
                  <th className="py-3 px-4 w-14"></th>
                  <th className="py-3 px-4">Товар</th>
                  <th className="py-3 px-4">Кабинет</th>
                  <th className="py-3 px-4 text-right">Цена</th>
                  <th className="py-3 px-4 text-right">Остаток</th>
                  <th className="py-3 px-2 w-8"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {products.map((p) => {
                  const expanded = expandedId === p.id
                  return (
                    <Fragment key={p.id}>
                      <tr
                        onClick={() => setExpandedId(expanded ? null : p.id)}
                        className="hover:bg-bg-subtle/40 transition-colors cursor-pointer"
                      >
                        <td className="py-3 px-4">
                          <div className="w-10 h-10 rounded-md bg-bg-subtle border border-border-subtle flex items-center justify-center overflow-hidden">
                            {p.image_url ? (
                              <img
                                src={p.image_url}
                                alt={p.name}
                                className="w-full h-full object-cover"
                              />
                            ) : (
                              <ImageIcon className="w-4 h-4 text-fg-subtle" />
                            )}
                          </div>
                        </td>
                        <td className="py-3 px-4 max-w-[420px]">
                          <div className="font-medium text-fg truncate">{p.name}</div>
                          <div className="flex items-center gap-2 text-[11px] text-fg-muted mt-0.5 flex-wrap">
                            <span className="font-mono">SKU {p.ozon_sku}</span>
                            <span>·</span>
                            <span className="font-mono truncate">{p.offer_id}</span>
                            <PriceIndexBadge value={p.price_index} />
                            {p.is_archived && (
                              <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-50 text-amber-700">
                                Архив
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          <div className="text-xs text-fg truncate">{p.cabinet_name}</div>
                          <div className="text-[10px] text-fg-subtle uppercase tracking-wider">
                            {p.cabinet_premium_tier.replace('_', ' ')}
                          </div>
                        </td>
                        <td className="py-3 px-4 text-right">
                          {(() => {
                            // Покупатель на витрине видит marketing_price (с СПП).
                            // current_price (исходная цена продавца) показываем
                            // зачёркнутой, если она ВЫШЕ чем marketing_price.
                            const visible = p.marketing_price ?? p.current_price
                            const showOriginal =
                              p.marketing_price != null &&
                              p.current_price != null &&
                              p.current_price > p.marketing_price
                            return visible != null ? (
                              <>
                                <div className="font-mono tabular-nums text-fg">
                                  {formatCurrency(visible)}
                                </div>
                                {showOriginal && (
                                  <div className="text-[10px] text-fg-subtle line-through tabular-nums">
                                    {formatCurrency(p.current_price as number)}
                                  </div>
                                )}
                              </>
                            ) : (
                              <span className="text-fg-subtle">—</span>
                            )
                          })()}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <StockBadge value={p.total_stock} />
                        </td>
                        <td className="py-3 px-2 text-fg-subtle">
                          <ChevronRight
                            className={cn(
                              'w-4 h-4 transition-transform',
                              expanded && 'rotate-90',
                            )}
                          />
                        </td>
                      </tr>
                      {expanded && (
                        <tr>
                          <td colSpan={6} className="bg-bg-subtle/30 px-6 py-3">
                            <StockBreakdown productId={p.id} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="px-4 py-2.5 text-[11px] text-fg-subtle border-t border-border-subtle">
            <AlertCircle className="w-3 h-3 inline mr-1 -mt-0.5" />
            Имена и фото подтянутся после enrichment-пасса через
            /v3/product/info/list (запущен).
          </div>
        </Card>
      )}
    </div>
  )
}
