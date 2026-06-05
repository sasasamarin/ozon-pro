/**
 * Модальное окно «Массовая правка» — теги, горячие, себестоимость.
 * Юзер: «упаковка 150₽ всем» → cost_price_add.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Loader2, Tag, Flame, DollarSign } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface Props {
  productIds: string[]
  onClose: () => void
}

export function BulkMetaModal({ productIds, onClose }: Props) {
  const qc = useQueryClient()
  const [addTag, setAddTag] = useState('')
  const [removeTag, setRemoveTag] = useState('')
  const [hotMode, setHotMode] = useState<'noop' | 'on' | 'off'>('noop')
  const [costMode, setCostMode] = useState<'noop' | 'set' | 'add'>('noop')
  const [costValue, setCostValue] = useState('')

  const apply = useMutation({
    mutationFn: async () => {
      const payload: any = { product_ids: productIds }
      if (addTag.trim())     payload.add_tags = [addTag.trim()]
      if (removeTag.trim())  payload.remove_tags = [removeTag.trim()]
      if (hotMode === 'on')  payload.is_hot = true
      if (hotMode === 'off') payload.is_hot = false
      if (costMode === 'set' && costValue) payload.cost_price = parseFloat(costValue)
      if (costMode === 'add' && costValue) payload.cost_price_add = parseFloat(costValue)
      return (await api.patch('/products/bulk/meta', payload)).data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['products'] })
      onClose()
    },
  })

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center p-0 sm:p-4 overflow-y-auto"
         onClick={onClose}>
      <Card className="max-w-lg w-full p-5 max-h-[90vh] overflow-y-auto rounded-b-none sm:rounded-lg" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold text-fg">Массовая правка</h2>
            <p className="text-xs text-fg-muted mt-0.5">
              Выбрано товаров: <strong className="text-fg">{productIds.length}</strong>
            </p>
          </div>
          <button onClick={onClose} className="text-fg-muted hover:text-fg">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-4 text-sm">
          {/* Теги */}
          <div className="border border-border-subtle rounded-md p-3 space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-medium text-fg-muted uppercase">
              <Tag className="w-3 h-3" /> Теги
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[10px] text-fg-muted mb-1">Добавить тег</label>
                <Input value={addTag} onChange={(e) => setAddTag(e.target.value)}
                       placeholder="напр. хит" />
              </div>
              <div>
                <label className="block text-[10px] text-fg-muted mb-1">Убрать тег</label>
                <Input value={removeTag} onChange={(e) => setRemoveTag(e.target.value)}
                       placeholder="напр. сезон" />
              </div>
            </div>
          </div>

          {/* 🔥 Горячий */}
          <div className="border border-border-subtle rounded-md p-3 space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-medium text-fg-muted uppercase">
              <Flame className="w-3 h-3" /> Горячие товары
            </div>
            <div className="flex gap-2">
              {([
                ['noop', 'Не менять'],
                ['on', '🔥 Сделать горячим'],
                ['off', 'Убрать "горячий"'],
              ] as const).map(([k, l]) => (
                <button key={k} onClick={() => setHotMode(k)} className={cn(
                  'flex-1 px-2 py-1.5 rounded border text-xs',
                  hotMode === k
                    ? 'border-fg bg-fg text-bg'
                    : 'border-border-subtle text-fg-muted hover:bg-bg-subtle',
                )}>
                  {l}
                </button>
              ))}
            </div>
          </div>

          {/* Себестоимость */}
          <div className="border border-border-subtle rounded-md p-3 space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-medium text-fg-muted uppercase">
              <DollarSign className="w-3 h-3" /> Себестоимость, ₽
            </div>
            <div className="flex gap-2">
              {([
                ['noop', 'Не менять'],
                ['set',  'Установить'],
                ['add',  '+к существующей'],
              ] as const).map(([k, l]) => (
                <button key={k} onClick={() => setCostMode(k)} className={cn(
                  'flex-1 px-2 py-1.5 rounded border text-xs',
                  costMode === k
                    ? 'border-fg bg-fg text-bg'
                    : 'border-border-subtle text-fg-muted hover:bg-bg-subtle',
                )}>
                  {l}
                </button>
              ))}
            </div>
            {costMode !== 'noop' && (
              <Input value={costValue} onChange={(e) => setCostValue(e.target.value)}
                     type="number" placeholder={costMode === 'add' ? 'напр. 150 (упаковка)' : 'напр. 1200'}
                     className="mt-2" />
            )}
            {costMode === 'add' && (
              <p className="text-[11px] text-fg-muted">
                Прибавится к текущей. Если у товара ещё нет себестоимости — поставится только эта надбавка.
              </p>
            )}
          </div>

          {apply.isError && (
            <div className="text-sm text-rose-700 bg-rose-50 px-3 py-2 rounded">
              Ошибка: {(apply.error as Error)?.message || 'неизвестно'}
            </div>
          )}
        </div>

        <div className="flex gap-2 mt-5 justify-end">
          <Button variant="ghost" onClick={onClose}>Отмена</Button>
          <Button onClick={() => apply.mutate()} disabled={apply.isPending}>
            {apply.isPending
              ? <Loader2 className="w-4 h-4 animate-spin" />
              : `Применить к ${productIds.length}`}
          </Button>
        </div>
      </Card>
    </div>
  )
}
