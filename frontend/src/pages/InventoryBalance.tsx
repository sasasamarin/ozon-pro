/**
 * «Товарный баланс» — сколько денег ЛЕЖИТ на складах Ozon.
 * Капитал в закупочной цене + потенциальная выручка по цене продажи.
 */
import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Loader2, Wallet, Info } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { SelectedProductBanner } from '@/components/SelectedProductBanner'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { useCabinetStore } from '@/stores/cabinet'

interface BalanceRow {
  product_id: string
  product_name: string
  offer_id: string
  ozon_sku: number
  cabinet_name: string
  category_name: string | null
  current_stock: number
  cost_price: number | null
  selling_price: number | null
  capital_at_cost: number
  capital_at_selling: number
  potential_margin: number
  margin_pct: number | null
}
interface GroupAgg {
  label: string; units: number
  capital_at_cost: number; capital_at_selling: number; potential_margin: number
}
interface BalanceResp {
  rows: BalanceRow[]
  totals: GroupAgg
  by_cabinet: GroupAgg[]
  by_category: GroupAgg[]
}

export function InventoryBalance() {
  const { selectedCabinetIds } = useCabinetStore()
  const [showArchived, setShowArchived] = useState(false)
  const [categoryFilter, setCategoryFilter] = useState<string>('')

  const { data, isLoading } = useQuery<BalanceResp>({
    queryKey: ['inventory', 'balance', selectedCabinetIds, showArchived],
    queryFn: async () => {
      const p = new URLSearchParams()
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      if (showArchived) p.append('include_archived', 'true')
      return (await api.get(`/inventory/balance?${p.toString()}`, { timeout: 60_000 })).data
    },
  })

  const filteredRows = useMemo(() => {
    if (!data) return []
    if (!categoryFilter) return data.rows
    return data.rows.filter((r) => r.category_name === categoryFilter)
  }, [data, categoryFilter])

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight flex items-center gap-2">
            <Wallet className="w-7 h-7 text-emerald-600" /> Товарный баланс
          </h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Сколько денег ЛЕЖИТ в товаре на складах Ozon. По себестоимости и продажной цене.
          </p>
        </div>
        <label className="flex items-center gap-2 text-xs text-fg-muted cursor-pointer">
          <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
          Показать архивные
        </label>
      </div>

      <SelectedProductBanner />

      {/* KPI блок */}
      {data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Card className="p-4" title="Сумма единиц на складах (free_to_sell − reserved)">
            <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">Единиц на складах</p>
            <p className="text-2xl font-semibold text-fg mt-1 tabular-nums">{formatNumber(data.totals.units)}</p>
          </Card>
          <Card className="p-4" title="Вложено в закупке (cost_price × qty)">
            <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">Капитал в закупке</p>
            <p className="text-2xl font-semibold text-rose-700 mt-1 tabular-nums">{formatCurrency(data.totals.capital_at_cost)}</p>
          </Card>
          <Card className="p-4" title="Если всё продать по текущей selling_price">
            <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">Потенциал выручки</p>
            <p className="text-2xl font-semibold text-emerald-700 mt-1 tabular-nums">{formatCurrency(data.totals.capital_at_selling)}</p>
          </Card>
          <Card className="p-4 border-emerald-200" title="Потенциальная маржа = выручка − закупка">
            <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">Потенциал маржи</p>
            <p className="text-2xl font-bold text-emerald-700 mt-1 tabular-nums">{formatCurrency(data.totals.potential_margin)}</p>
          </Card>
        </div>
      )}

      {/* Группировка */}
      {data && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card className="p-4">
            <h3 className="text-sm font-semibold text-fg mb-3">По кабинетам</h3>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-fg-muted uppercase text-[10px]">
                  <th className="text-left py-1.5">Кабинет</th>
                  <th className="text-right py-1.5">qty</th>
                  <th className="text-right py-1.5">в закупке</th>
                  <th className="text-right py-1.5">в продаже</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {data.by_cabinet.map((g) => (
                  <tr key={g.label}>
                    <td className="py-1.5 font-medium">{g.label}</td>
                    <td className="py-1.5 text-right tabular-nums">{formatNumber(g.units)}</td>
                    <td className="py-1.5 text-right tabular-nums text-rose-700">{formatCurrency(g.capital_at_cost)}</td>
                    <td className="py-1.5 text-right tabular-nums text-emerald-700">{formatCurrency(g.capital_at_selling)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card className="p-4">
            <h3 className="text-sm font-semibold text-fg mb-3">По категориям</h3>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-fg-muted uppercase text-[10px]">
                  <th className="text-left py-1.5">Категория</th>
                  <th className="text-right py-1.5">qty</th>
                  <th className="text-right py-1.5">в закупке</th>
                  <th className="text-right py-1.5">в продаже</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {data.by_category.slice(0, 10).map((g) => (
                  <tr key={g.label} className={cn('cursor-pointer hover:bg-bg-subtle/50',
                    categoryFilter === g.label && 'bg-bg-subtle')}
                      onClick={() => setCategoryFilter(categoryFilter === g.label ? '' : g.label)}>
                    <td className="py-1.5 font-medium truncate max-w-[200px]" title={g.label}>{g.label}</td>
                    <td className="py-1.5 text-right tabular-nums">{formatNumber(g.units)}</td>
                    <td className="py-1.5 text-right tabular-nums text-rose-700">{formatCurrency(g.capital_at_cost)}</td>
                    <td className="py-1.5 text-right tabular-nums text-emerald-700">{formatCurrency(g.capital_at_selling)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {categoryFilter && (
              <p className="text-[11px] text-fg-muted mt-2">
                Фильтр: <strong>{categoryFilter}</strong>
                <button onClick={() => setCategoryFilter('')} className="ml-2 text-blue-700 hover:underline">сбросить</button>
              </p>
            )}
          </Card>
        </div>
      )}

      {/* Per-product таблица */}
      <Card className="overflow-hidden">
        <div className="px-4 py-3 border-b border-border-subtle">
          <h3 className="text-sm font-semibold text-fg">Товары на складах ({filteredRows.length})</h3>
        </div>
        {isLoading ? (
          <div className="py-16 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-fg-muted" /></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                <tr className="text-fg-muted uppercase">
                  <th className="text-left py-2 px-3">Товар</th>
                  <th className="text-left py-2 px-2">Категория</th>
                  <th className="text-right py-2 px-2">qty</th>
                  <th className="text-right py-2 px-2">Себест.</th>
                  <th className="text-right py-2 px-2">Цена прод.</th>
                  <th className="text-right py-2 px-2">Капитал (закупка)</th>
                  <th className="text-right py-2 px-2">Капитал (продажа)</th>
                  <th className="text-right py-2 px-2">Потенциал маржи</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {filteredRows.slice(0, 200).map((r) => (
                  <tr key={r.product_id} className="hover:bg-bg-subtle/40">
                    <td className="py-2 px-3">
                      <Link to={`/products/${r.product_id}`} className="font-medium text-fg hover:text-blue-700 truncate block max-w-[260px]" title={r.product_name}>
                        {r.product_name}
                      </Link>
                      <div className="text-[10px] text-fg-subtle font-mono">
                        {r.offer_id} · {r.cabinet_name}
                      </div>
                    </td>
                    <td className="py-2 px-2 text-fg-muted truncate max-w-[140px]" title={r.category_name || ''}>
                      {r.category_name || '—'}
                    </td>
                    <td className="text-right py-2 px-2 tabular-nums font-semibold">{formatNumber(r.current_stock)}</td>
                    <td className="text-right py-2 px-2 tabular-nums">
                      {r.cost_price != null ? formatCurrency(r.cost_price) : <span className="text-amber-700">⚠</span>}
                    </td>
                    <td className="text-right py-2 px-2 tabular-nums">
                      {r.selling_price != null ? formatCurrency(r.selling_price) : '—'}
                    </td>
                    <td className="text-right py-2 px-2 tabular-nums text-rose-700">{formatCurrency(r.capital_at_cost)}</td>
                    <td className="text-right py-2 px-2 tabular-nums text-emerald-700">{formatCurrency(r.capital_at_selling)}</td>
                    <td className={cn('text-right py-2 px-2 tabular-nums font-semibold',
                      r.potential_margin >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
                      {formatCurrency(r.potential_margin)}
                      {r.margin_pct != null && (
                        <span className="text-[10px] text-fg-subtle ml-1">{r.margin_pct.toFixed(0)}%</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filteredRows.length > 200 && (
              <p className="text-xs text-fg-subtle p-3">Показано 200 из {filteredRows.length}</p>
            )}
          </div>
        )}
      </Card>

      {/* Объяснение */}
      <Card className="p-4 bg-blue-50/60 border-blue-200/60 text-sm text-blue-900/90">
        <div className="flex items-start gap-2">
          <Info className="w-4 h-4 text-blue-700 mt-0.5 shrink-0" />
          <div>
            <strong>Как считается:</strong> остаток (FBO_WH с приоритетом, либо AGG/FBO/FBS — без дублей)
            × себестоимость = вложено в товар. × selling_price = потенциальная выручка.
            Разница = потенциальная маржа. Если потенциал низкий — товар «лежит мёртвым грузом».
          </div>
        </div>
      </Card>
    </div>
  )
}
