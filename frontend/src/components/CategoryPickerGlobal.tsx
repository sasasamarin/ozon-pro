/**
 * Глобальный пикер категории в Topbar.
 * Single-select из дерева Ozon (9550 узлов в БД, скрываем пустые).
 * Поиск по имени или ID. При выборе родительской категории — её потомки в скоупе.
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FolderTree, X, ChevronDown, ChevronRight, Search, Package } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useCategoryFilter } from '@/stores/category_filter'

interface TreeNode {
  ozon_id: number
  name: string
  full_path: string
  level: number
  is_type: boolean
  is_disabled: boolean
  sku_count: number
  children: TreeNode[]
}

interface TreeResp {
  tree: TreeNode[]
  nodes_in_db: number
}

export function CategoryPickerGlobal() {
  const { selectedCategoryId, selectedCategoryName, selectedCategoryPath, setSelectedCategory, clear } =
    useCategoryFilter()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const ref = useRef<HTMLDivElement>(null)

  const { data, isLoading } = useQuery<TreeResp>({
    queryKey: ['categories-tree-picker'],
    queryFn: async () => (await api.get('/products/categories/tree?hide_empty=true&days=90')).data,
    staleTime: 10 * 60_000,
  })

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  // При открытии — разворачиваем верхний уровень
  useEffect(() => {
    if (open && data && expanded.size === 0) {
      setExpanded(new Set(data.tree.map((n) => n.ozon_id)))
    }
  }, [open, data, expanded.size])

  // Плоский список с фильтром поиска (если есть поиск — показываем матчи без структуры)
  const flatSearch = useMemo(() => {
    if (!search || !data) return null
    const q = search.toLowerCase()
    const result: TreeNode[] = []
    const walk = (nodes: TreeNode[]) => {
      for (const n of nodes) {
        if (n.name.toLowerCase().includes(q) || n.full_path.toLowerCase().includes(q) ||
            String(n.ozon_id) === q) {
          result.push(n)
        }
        if (n.children.length > 0) walk(n.children)
      }
    }
    walk(data.tree)
    return result.slice(0, 100)
  }, [search, data])

  const toggleExpanded = (id: number) =>
    setExpanded((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const buttonLabel = selectedCategoryName
    ? (selectedCategoryName.length > 22 ? selectedCategoryName.slice(0, 22) + '…' : selectedCategoryName)
    : 'Все категории'

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'inline-flex items-center gap-1.5 h-9 px-3 rounded-md border text-sm transition-colors',
          selectedCategoryId
            ? 'border-amber-500/40 bg-amber-50/40 text-amber-900'
            : 'border-border-subtle bg-bg hover:bg-bg-subtle text-fg-muted',
        )}
        title={selectedCategoryPath || 'Выбрать категорию для фильтра'}
      >
        <FolderTree className="w-4 h-4" />
        <span className="font-medium max-w-[180px] truncate">{buttonLabel}</span>
        <ChevronDown className="w-3.5 h-3.5 opacity-60" />
      </button>

      {open && (
        <div className="absolute right-0 top-11 z-50 w-[420px] bg-bg border border-border rounded-lg shadow-elev">
          <div className="p-2 border-b border-border-subtle flex items-center gap-2">
            <Search className="w-4 h-4 text-fg-muted" />
            <input
              type="search"
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск по имени / ID / пути"
              className="flex-1 bg-transparent outline-none text-sm"
            />
            {selectedCategoryId && (
              <button
                onClick={() => { clear(); setOpen(false); setSearch('') }}
                className="text-xs text-rose-700 hover:underline inline-flex items-center gap-1"
              >
                <X className="w-3.5 h-3.5" /> сбросить
              </button>
            )}
          </div>

          <button
            onClick={() => { clear(); setOpen(false); setSearch('') }}
            className={cn(
              'w-full text-left px-3 py-2 text-sm border-b border-border-subtle hover:bg-bg-subtle',
              !selectedCategoryId && 'bg-bg-subtle font-semibold',
            )}
          >
            <FolderTree className="w-3.5 h-3.5 inline mr-1.5" />
            Все категории (агрегат)
          </button>

          <div className="max-h-[420px] overflow-y-auto">
            {isLoading && <div className="p-4 text-sm text-fg-muted text-center">Загрузка дерева…</div>}
            {!isLoading && data && data.tree.length === 0 && (
              <div className="p-4 text-sm text-fg-muted text-center">
                Дерево не синкнуто. Запусти sync_category_tree.
              </div>
            )}
            {flatSearch ? (
              <div>
                {flatSearch.map((n) => (
                  <button
                    key={n.ozon_id}
                    onClick={() => {
                      setSelectedCategory(n.ozon_id, n.name, n.full_path)
                      setOpen(false); setSearch('')
                    }}
                    className={cn(
                      'w-full text-left px-3 py-1.5 text-xs hover:bg-bg-subtle border-b border-border-subtle/40',
                      selectedCategoryId === n.ozon_id && 'bg-amber-50',
                    )}
                  >
                    <div className="flex items-center gap-1.5">
                      {n.is_type
                        ? <Package className="w-3.5 h-3.5 text-fg-subtle" />
                        : <FolderTree className="w-3.5 h-3.5 text-amber-600" />}
                      <span className="font-medium text-fg truncate">{n.name}</span>
                      <span className="text-fg-subtle ml-auto">SKU: {n.sku_count}</span>
                    </div>
                    <div className="text-fg-subtle text-[10px] pl-5 truncate">{n.full_path}</div>
                  </button>
                ))}
                {flatSearch.length === 0 && (
                  <div className="p-4 text-sm text-fg-muted text-center">Ничего не найдено</div>
                )}
              </div>
            ) : data && data.tree.map((node) => (
              <TreeRow
                key={node.ozon_id}
                node={node}
                expanded={expanded}
                onToggle={toggleExpanded}
                selectedId={selectedCategoryId}
                onSelect={(n) => {
                  setSelectedCategory(n.ozon_id, n.name, n.full_path)
                  setOpen(false)
                }}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function TreeRow({
  node, expanded, onToggle, selectedId, onSelect,
}: {
  node: TreeNode
  expanded: Set<number>
  onToggle: (id: number) => void
  selectedId: number | null
  onSelect: (n: TreeNode) => void
}) {
  const hasChildren = node.children.length > 0
  const isOpen = expanded.has(node.ozon_id)
  const indent = node.level * 14

  return (
    <>
      <div className={cn(
        'flex items-center hover:bg-bg-subtle border-b border-border-subtle/40 text-xs',
        selectedId === node.ozon_id && 'bg-amber-50',
        node.is_disabled && 'opacity-50',
      )}>
        <div className="flex items-center" style={{ paddingLeft: indent }}>
          {hasChildren ? (
            <button
              onClick={() => onToggle(node.ozon_id)}
              className="w-5 h-5 flex items-center justify-center text-fg-muted hover:text-fg"
            >
              {isOpen
                ? <ChevronDown className="w-3 h-3" />
                : <ChevronRight className="w-3 h-3" />}
            </button>
          ) : (
            <span className="w-5" />
          )}
        </div>
        <button
          onClick={() => onSelect(node)}
          className="flex-1 text-left px-1.5 py-1.5 flex items-center gap-1.5"
        >
          {node.is_type
            ? <Package className="w-3.5 h-3.5 text-fg-subtle flex-shrink-0" />
            : <FolderTree className="w-3.5 h-3.5 text-amber-600 flex-shrink-0" />}
          <span className="font-medium text-fg truncate">{node.name}</span>
          <span className="text-fg-subtle ml-auto pl-2 flex-shrink-0">{node.sku_count || ''}</span>
        </button>
      </div>
      {isOpen && node.children.map((c) => (
        <TreeRow
          key={c.ozon_id}
          node={c}
          expanded={expanded}
          onToggle={onToggle}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      ))}
    </>
  )
}
