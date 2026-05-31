/**
 * Глобальный пикер товара в Topbar — справа от Cabinet-свитчера.
 * Автокомплит-поиск по имени / offer_id / sku. Single-select.
 * При выборе товара ВСЕ разделы пересчитываются на этого товара (если поддерживают product_id).
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Package, X, ChevronDown, Search } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useProductFilter } from '@/stores/product_filter'
import { useCabinetStore } from '@/stores/cabinet'

interface ProductRow {
  id: string
  name: string
  offer_id: string
  ozon_sku: number
  is_archived: boolean
  cabinet_name: string
}

export function ProductPickerGlobal() {
  const { selectedProductId, selectedProductName, setSelectedProduct, clear } = useProductFilter()
  const { selectedCabinetIds } = useCabinetStore()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  const { data: products = [], isLoading } = useQuery<ProductRow[]>({
    queryKey: ['products', 'picker', selectedCabinetIds],
    queryFn: async () => {
      const p = new URLSearchParams()
      selectedCabinetIds.forEach((id) => p.append('cabinet_ids', id))
      return (await api.get(`/products/?${p.toString()}`)).data
    },
    staleTime: 60_000,
  })

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  // Фильтрация поиска
  const filtered = useMemo(() => {
    if (!search) return products.filter((p) => !p.is_archived).slice(0, 50)
    const q = search.toLowerCase()
    return products.filter((p) =>
      p.name.toLowerCase().includes(q) ||
      p.offer_id.toLowerCase().includes(q) ||
      String(p.ozon_sku).includes(q)
    ).slice(0, 50)
  }, [products, search])

  const buttonLabel = selectedProductName
    ? (selectedProductName.length > 26 ? selectedProductName.slice(0, 26) + '…' : selectedProductName)
    : 'Все товары'

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'inline-flex items-center gap-1.5 h-9 px-3 rounded-md border text-sm transition-colors',
          selectedProductId
            ? 'border-blue-500/40 bg-blue-50/40 text-blue-900'
            : 'border-border-subtle bg-bg hover:bg-bg-subtle text-fg-muted',
        )}
        title={selectedProductName || 'Выбрать товар для фильтра во всех разделах'}
      >
        <Package className="w-4 h-4" />
        <span className="font-medium max-w-[200px] truncate">{buttonLabel}</span>
        <ChevronDown className="w-3.5 h-3.5 opacity-60" />
      </button>

      {open && (
        <div className="absolute right-0 top-11 z-50 w-96 bg-bg border border-border rounded-lg shadow-elev animate-fade-in">
          {/* Поиск */}
          <div className="p-2 border-b border-border-subtle flex items-center gap-2">
            <Search className="w-4 h-4 text-fg-muted" />
            <input
              type="search"
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск: имя / offer_id / sku"
              className="flex-1 bg-transparent outline-none text-sm text-fg placeholder-fg-subtle"
            />
            {selectedProductId && (
              <button
                onClick={() => { clear(); setOpen(false); setSearch('') }}
                className="text-xs text-rose-700 hover:underline inline-flex items-center gap-1"
              >
                <X className="w-3.5 h-3.5" /> сбросить
              </button>
            )}
          </div>

          {/* «Все товары» опция */}
          <button
            onClick={() => { clear(); setOpen(false); setSearch('') }}
            className={cn(
              'w-full text-left px-3 py-2 text-sm border-b border-border-subtle hover:bg-bg-subtle',
              !selectedProductId && 'bg-bg-subtle font-semibold',
            )}
          >
            <Package className="w-3.5 h-3.5 inline mr-1.5" />
            Все товары (агрегат)
          </button>

          {/* Список товаров */}
          <div className="max-h-[400px] overflow-y-auto">
            {isLoading && <div className="p-4 text-sm text-fg-muted text-center">Загрузка…</div>}
            {!isLoading && filtered.length === 0 && (
              <div className="p-4 text-sm text-fg-muted text-center">Ничего не найдено</div>
            )}
            {filtered.map((p) => (
              <button
                key={p.id}
                onClick={() => { setSelectedProduct(p.id, p.name); setOpen(false); setSearch('') }}
                className={cn(
                  'w-full text-left px-3 py-2 text-xs hover:bg-bg-subtle border-b border-border-subtle/40',
                  selectedProductId === p.id && 'bg-blue-50',
                )}
              >
                <div className="font-medium text-fg truncate" title={p.name}>{p.name}</div>
                <div className="text-fg-subtle font-mono text-[10px]">
                  {p.offer_id} · sku {p.ozon_sku} · {p.cabinet_name}
                </div>
              </button>
            ))}
            {!isLoading && products.length > 50 && (
              <div className="p-2 text-[11px] text-fg-subtle text-center">
                Показано 50, уточни поиск
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
