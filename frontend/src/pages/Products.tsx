import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Package, AlertCircle, Image as ImageIcon, Store } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { api } from '@/lib/api'
import { formatCurrency, cn } from '@/lib/utils'
import { getErrorMessage } from '@/lib/errors'

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

export function Products() {
  const { data, isLoading, error } = useQuery<ProductItem[]>({
    queryKey: ['products'],
    queryFn: async () => {
      const res = await api.get('/products/')
      return res.data
    },
  })

  const products = data || []

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Товары</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            {isLoading
              ? 'Загрузка…'
              : products.length === 0
                ? 'Товары не подгружены'
                : `Всего товаров: ${products.length}`}
          </p>
        </div>
        <Link to="/cabinets">
          <Button variant="secondary">
            <Store className="w-4 h-4" />К кабинетам
          </Button>
        </Link>
      </div>

      {error && (
        <div className="text-sm text-error bg-red-50 border border-red-200 rounded-md px-3 py-2">
          {getErrorMessage(error)}
        </div>
      )}

      {isLoading ? (
        <Card className="p-12 flex items-center justify-center text-fg-muted">
          Загрузка товаров…
        </Card>
      ) : products.length === 0 ? (
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
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {products.map((p) => (
                  <tr key={p.id} className="hover:bg-bg-subtle/40 transition-colors">
                    <td className="py-3 px-4">
                      <div className="w-10 h-10 rounded-md bg-bg-subtle border border-border-subtle flex items-center justify-center overflow-hidden">
                        {p.image_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
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
                      <div className="flex items-center gap-2 text-[11px] text-fg-muted mt-0.5">
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
                      {p.current_price != null ? (
                        <div className="font-mono tabular-nums text-fg">
                          {formatCurrency(p.current_price)}
                        </div>
                      ) : (
                        <span className="text-fg-subtle">—</span>
                      )}
                      {p.old_price != null && p.current_price != null && p.old_price > p.current_price && (
                        <div className="text-[10px] text-fg-subtle line-through tabular-nums">
                          {formatCurrency(p.old_price)}
                        </div>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <StockBadge value={p.total_stock} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-4 py-2.5 text-[11px] text-fg-subtle border-t border-border-subtle">
            <AlertCircle className="w-3 h-3 inline mr-1 -mt-0.5" />
            Имена и фото — заглушки (Ozon /v3/product/list их не отдаёт). Полные данные после интеграции /v3/product/info/list.
          </div>
        </Card>
      )}
    </div>
  )
}
