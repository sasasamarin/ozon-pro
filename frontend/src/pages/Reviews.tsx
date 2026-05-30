import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Star, Loader2, MessageCircle, Image as ImageIcon } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface ReviewRow {
  id: string
  cabinet_name: string
  product_id: string | null
  product_name: string | null
  offer_id: string | null
  author: string | null
  rating: number | null
  text: string | null
  pluses: string | null
  minuses: string | null
  has_photos: boolean
  has_videos: boolean
  has_answer: boolean
  status: string | null
  created_at_ozon: string | null
}

export function Reviews() {
  const [rating, setRating] = useState<number | undefined>(undefined)
  const [days, setDays] = useState(90)

  const { data, isLoading } = useQuery<ReviewRow[]>({
    queryKey: ['reviews', days, rating],
    queryFn: async () => {
      const params = new URLSearchParams({ days: String(days) })
      if (rating) params.append('rating', String(rating))
      return (await api.get(`/communications/reviews?${params.toString()}`)).data
    },
  })

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Отзывы</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          {data?.length ?? 0} отзывов · Premium Pro only (Ozon)
        </p>
      </div>

      <div className="flex gap-2 flex-wrap">
        <span className="text-sm text-fg-muted self-center mr-2">Рейтинг:</span>
        {[undefined, 1, 2, 3, 4, 5].map((r, i) => (
          <button key={i} onClick={() => setRating(r)} className={cn(
            'px-3 py-1.5 rounded-md text-sm border transition-colors flex items-center gap-1',
            rating === r ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
          )}>
            {r === undefined ? 'Все' : <>
              {r}<Star className="w-3 h-3" />
            </>}
          </button>
        ))}
        <div className="flex gap-2 ml-auto">
          {[7, 28, 30, 90, 365].map((d) => (
            <button key={d} onClick={() => setDays(d)} className={cn(
              'px-3 py-1.5 rounded-md text-sm border transition-colors',
              days === d ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
            )}>
              {d === 30 && '30 дней'}{d === 90 && '90 дней'}{d === 365 && 'Год'}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <Card className="py-16 flex justify-center"><Loader2 className="w-5 h-5 animate-spin" /></Card>
      ) : (data?.length ?? 0) === 0 ? (
        <Card className="py-12 flex flex-col items-center text-fg-muted text-sm">
          <MessageCircle className="w-8 h-8 mb-2 text-fg-subtle" />
          <p>Отзывов нет. Premium Pro тариф включает синхронизацию.</p>
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {data!.map((r) => (
            <Card key={r.id} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    {r.rating != null && (
                      <div className="flex">
                        {[1, 2, 3, 4, 5].map((i) => (
                          <Star key={i} className={cn('w-4 h-4',
                            i <= r.rating! ? 'text-amber-500 fill-amber-500' : 'text-fg-subtle/30')} />
                        ))}
                      </div>
                    )}
                    <span className="text-sm font-medium text-fg">{r.author || 'Аноним'}</span>
                    <span className="text-xs text-fg-muted">{r.cabinet_name}</span>
                    {r.has_photos && <ImageIcon className="w-3 h-3 text-fg-subtle" />}
                    {r.created_at_ozon && (
                      <span className="text-xs text-fg-subtle ml-auto">
                        {new Date(r.created_at_ozon).toLocaleDateString('ru-RU')}
                      </span>
                    )}
                  </div>
                  {r.product_name && (
                    <div className="text-xs text-fg-muted mt-1 font-mono">{r.offer_id} · {r.product_name}</div>
                  )}
                  {r.text && <p className="text-sm text-fg mt-2 leading-relaxed">{r.text}</p>}
                  {r.pluses && <p className="text-sm text-emerald-700 mt-1.5"><strong>+</strong> {r.pluses}</p>}
                  {r.minuses && <p className="text-sm text-rose-700 mt-1.5"><strong>−</strong> {r.minuses}</p>}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
