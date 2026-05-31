/**
 * Глобальный multi-select пикер тегов в Topbar.
 * Список из реально используемых product.tags.
 * Multi-select OR: товар должен иметь хотя бы один из выбранных тегов.
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Tag, X, ChevronDown, Check, Search } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useTagFilter } from '@/stores/tag_filter'

interface TagRow {
  tag: string
  count: number
}

export function TagPickerGlobal() {
  const { selectedTags, toggleTag, clear } = useTagFilter()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  const { data: tags = [], isLoading } = useQuery<TagRow[]>({
    queryKey: ['tags-list'],
    queryFn: async () => (await api.get('/products/tags-list')).data,
    staleTime: 5 * 60_000,
  })

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const filtered = useMemo(() => {
    if (!search) return tags
    const q = search.toLowerCase()
    return tags.filter((t) => t.tag.toLowerCase().includes(q))
  }, [tags, search])

  const buttonLabel = selectedTags.length === 0
    ? 'Все теги'
    : selectedTags.length === 1
      ? selectedTags[0]
      : `${selectedTags.length} тегов`

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'inline-flex items-center gap-1.5 h-9 px-3 rounded-md border text-sm transition-colors',
          selectedTags.length > 0
            ? 'border-violet-500/40 bg-violet-50/40 text-violet-900'
            : 'border-border-subtle bg-bg hover:bg-bg-subtle text-fg-muted',
        )}
        title={selectedTags.length > 0 ? `Выбрано: ${selectedTags.join(', ')}` : 'Фильтр по тегам товаров'}
      >
        <Tag className="w-4 h-4" />
        <span className="font-medium max-w-[140px] truncate">{buttonLabel}</span>
        <ChevronDown className="w-3.5 h-3.5 opacity-60" />
      </button>

      {open && (
        <div className="absolute right-0 top-11 z-50 w-72 bg-bg border border-border rounded-lg shadow-elev">
          <div className="p-2 border-b border-border-subtle flex items-center gap-2">
            <Search className="w-4 h-4 text-fg-muted" />
            <input
              type="search"
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Найти тег"
              className="flex-1 bg-transparent outline-none text-sm"
            />
            {selectedTags.length > 0 && (
              <button
                onClick={() => { clear() }}
                className="text-xs text-rose-700 hover:underline inline-flex items-center gap-1"
              >
                <X className="w-3.5 h-3.5" /> сбросить
              </button>
            )}
          </div>

          <div className="max-h-[400px] overflow-y-auto py-1">
            {isLoading && <div className="p-4 text-sm text-fg-muted text-center">Загрузка…</div>}
            {!isLoading && tags.length === 0 && (
              <div className="p-4 text-sm text-fg-muted text-center">
                Тегов нет. Добавь товарам в карточке.
              </div>
            )}
            {filtered.map((t) => {
              const isOn = selectedTags.includes(t.tag)
              return (
                <button
                  key={t.tag}
                  onClick={() => toggleTag(t.tag)}
                  className={cn(
                    'w-full flex items-center justify-between gap-2 px-3 py-1.5 text-xs hover:bg-bg-subtle',
                    isOn && 'bg-violet-50/60',
                  )}
                >
                  <div className="flex items-center gap-2">
                    <div className={cn(
                      'w-4 h-4 rounded border flex items-center justify-center',
                      isOn ? 'bg-violet-600 border-violet-600' : 'border-border-subtle',
                    )}>
                      {isOn && <Check className="w-3 h-3 text-white" />}
                    </div>
                    <span className={cn('font-medium', isOn && 'text-violet-900')}>{t.tag}</span>
                  </div>
                  <span className="text-fg-subtle">{t.count}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
