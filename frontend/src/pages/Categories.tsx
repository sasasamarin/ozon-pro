import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FolderTree, Loader2, ChevronRight, ChevronDown, Package } from 'lucide-react'
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

interface FlatResp {
  period_from: string
  period_to: string
  total_revenue: number
  rows: CategoryRow[]
}

interface TreeNode {
  ozon_id: number
  name: string
  full_path: string
  level: number
  is_type: boolean
  is_disabled: boolean
  sku_count: number
  revenue: number
  delivered_units: number
  cogs: number
  gross_profit: number
  gross_margin_pct: number | null
  children: TreeNode[]
}

interface TreeResp {
  period_from: string
  period_to: string
  total_revenue: number
  nodes_in_db: number
  tree: TreeNode[]
}

export function Categories() {
  const { selectedCabinetIds } = useCabinetStore()
  const [days, setDays] = useState(30)
  const [view, setView] = useState<'tree' | 'flat'>('tree')
  const [hideEmpty, setHideEmpty] = useState(true)

  const { data: flatData, isLoading: flatLoading } = useQuery<FlatResp>({
    queryKey: ['categories-flat', selectedCabinetIds, days],
    enabled: view === 'flat',
    queryFn: async () => {
      const p = new URLSearchParams({ days: String(days) })
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      return (await api.get(`/products/categories/?${p.toString()}`)).data
    },
  })

  const { data: treeData, isLoading: treeLoading } = useQuery<TreeResp>({
    queryKey: ['categories-tree', selectedCabinetIds, days, hideEmpty],
    enabled: view === 'tree',
    queryFn: async () => {
      const p = new URLSearchParams({ days: String(days), hide_empty: String(hideEmpty) })
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      return (await api.get(`/products/categories/tree?${p.toString()}`)).data
    },
  })

  const totalRevenue = view === 'tree' ? treeData?.total_revenue : flatData?.total_revenue
  const itemsCount = view === 'tree'
    ? countLeaves(treeData?.tree || [])
    : (flatData?.rows.length ?? 0)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Категории</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            {itemsCount} категорий с продажами · общая выручка {formatCurrency(totalRevenue ?? 0)}
            {view === 'tree' && treeData && (
              <span className="ml-2 text-fg-subtle">· каталог Ozon: {formatNumber(treeData.nodes_in_db)} узлов</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="inline-flex rounded-md border border-border-subtle overflow-hidden">
            <button onClick={() => setView('tree')} className={cn(
              'px-3 py-1.5 text-sm transition-colors',
              view === 'tree' ? 'bg-fg text-bg' : 'text-fg-muted hover:bg-bg-subtle',
            )}>Дерево</button>
            <button onClick={() => setView('flat')} className={cn(
              'px-3 py-1.5 text-sm transition-colors',
              view === 'flat' ? 'bg-fg text-bg' : 'text-fg-muted hover:bg-bg-subtle',
            )}>Список</button>
          </div>
          {view === 'tree' && (
            <label className="flex items-center gap-1.5 text-xs text-fg-muted cursor-pointer">
              <input type="checkbox" checked={hideEmpty} onChange={(e) => setHideEmpty(e.target.checked)} />
              скрыть пустые ветки
            </label>
          )}
          <div className="flex gap-2">
            {[7, 30, 90, 365].map((d) => (
              <button key={d} onClick={() => setDays(d)} className={cn(
                'px-3 py-1.5 rounded-md text-sm border transition-colors',
                days === d ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
              )}>
                {d === 7 && '7д'}{d === 30 && '30д'}{d === 90 && '90д'}{d === 365 && 'Год'}
              </button>
            ))}
          </div>
        </div>
      </div>

      <Card className="overflow-hidden">
        {(view === 'tree' ? treeLoading : flatLoading) ? (
          <div className="py-16 flex justify-center text-fg-muted">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : view === 'tree' && treeData?.tree.length === 0 ? (
          <div className="py-16 text-center text-fg-muted">
            <FolderTree className="w-10 h-10 mx-auto mb-2 text-fg-subtle" />
            <p>Дерево категорий ещё не синкнуто или у тебя нет продаж в этих категориях.</p>
            <p className="text-xs mt-1">Запусти sync_category_tree task или сними чекбокс «скрыть пустые ветки».</p>
          </div>
        ) : view === 'tree' ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                  <th className="py-2.5 px-4 font-medium">категория</th>
                  <th className="py-2.5 px-4 font-medium text-right">SKU</th>
                  <th className="py-2.5 px-4 font-medium text-right">шт</th>
                  <th className="py-2.5 px-4 font-medium text-right">выручка</th>
                  <th className="py-2.5 px-4 font-medium text-right">COGS</th>
                  <th className="py-2.5 px-4 font-medium text-right">валовая</th>
                  <th className="py-2.5 px-4 font-medium text-right">маржа %</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {(treeData?.tree || []).map((node) => (
                  <TreeRow key={node.ozon_id} node={node} />
                ))}
              </tbody>
            </table>
          </div>
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
                {(flatData?.rows || []).map((r) => (
                  <tr key={r.category_name} className="hover:bg-bg-subtle/40">
                    <td className="py-2.5 px-4">
                      <div className="flex items-center gap-2">
                        <Package className="w-4 h-4 text-fg-subtle" />
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

function TreeRow({ node }: { node: TreeNode }) {
  // По умолчанию: разворачиваем первые два уровня корня — обычно их немного и юзер видит структуру
  const [expanded, setExpanded] = useState(node.level < 1)
  const hasChildren = node.children.length > 0
  const indent = node.level * 16

  return (
    <>
      <tr className={cn(
        'hover:bg-bg-subtle/40',
        node.is_disabled && 'opacity-50',
        node.level === 0 && 'bg-bg-subtle/20 font-medium',
      )}>
        <td className="py-2 px-4">
          <div className="flex items-center gap-1" style={{ paddingLeft: indent }}>
            {hasChildren ? (
              <button
                onClick={() => setExpanded((e) => !e)}
                className="w-5 h-5 flex items-center justify-center text-fg-muted hover:text-fg rounded hover:bg-bg-subtle"
              >
                {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              </button>
            ) : (
              <span className="w-5" />
            )}
            {node.is_type ? (
              <Package className="w-3.5 h-3.5 text-fg-subtle flex-shrink-0" />
            ) : (
              <FolderTree className="w-3.5 h-3.5 text-amber-600 flex-shrink-0" />
            )}
            <span className="text-fg truncate">{node.name}</span>
          </div>
        </td>
        <td className="py-2 px-4 text-right tabular-nums">{node.sku_count || ''}</td>
        <td className="py-2 px-4 text-right tabular-nums">{node.delivered_units ? formatNumber(node.delivered_units) : ''}</td>
        <td className="py-2 px-4 text-right tabular-nums text-emerald-700">
          {node.revenue > 0 ? formatCurrency(node.revenue) : ''}
        </td>
        <td className="py-2 px-4 text-right tabular-nums text-rose-700">
          {node.cogs > 0 ? `−${formatCurrency(node.cogs)}` : ''}
        </td>
        <td className={cn('py-2 px-4 text-right tabular-nums font-semibold',
          node.gross_profit > 0 ? 'text-emerald-700' : node.gross_profit < 0 ? 'text-rose-700' : 'text-fg-subtle')}>
          {node.gross_profit !== 0 ? formatCurrency(node.gross_profit) : ''}
        </td>
        <td className="py-2 px-4 text-right tabular-nums">
          {node.gross_margin_pct != null ? `${node.gross_margin_pct}%` : ''}
        </td>
      </tr>
      {expanded && node.children.map((c) => <TreeRow key={c.ozon_id} node={c} />)}
    </>
  )
}

function countLeaves(tree: TreeNode[]): number {
  let n = 0
  const walk = (nodes: TreeNode[]): void => {
    for (const node of nodes) {
      if (node.sku_count > 0 && node.children.length === 0) n++
      if (node.children.length > 0) walk(node.children)
    }
  }
  walk(tree)
  return n
}
