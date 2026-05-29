import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { HelpCircle, Loader2, MessageSquare } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface QuestionRow {
  id: string
  cabinet_name: string
  product_id: string | null
  product_name: string | null
  offer_id: string | null
  author: string | null
  text: string
  answer: string | null
  created_at_ozon: string | null
  answer_date: string | null
  status: string | null
}

export function Questions() {
  const [onlyUnanswered, setOnlyUnanswered] = useState(false)
  const [days, setDays] = useState(90)

  const { data, isLoading } = useQuery<QuestionRow[]>({
    queryKey: ['questions', days, onlyUnanswered],
    queryFn: async () => {
      const params = new URLSearchParams({ days: String(days), only_unanswered: String(onlyUnanswered) })
      return (await api.get(`/communications/questions?${params.toString()}`)).data
    },
  })

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Вопросы покупателей</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          {data?.length ?? 0} вопросов · Premium Pro only
        </p>
      </div>

      <div className="flex gap-2 flex-wrap">
        <button onClick={() => setOnlyUnanswered(!onlyUnanswered)} className={cn(
          'px-3 py-1.5 rounded-md text-sm border transition-colors',
          onlyUnanswered ? 'border-rose-300 bg-rose-50 text-rose-700' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
        )}>
          {onlyUnanswered ? 'Только без ответа' : 'Все вопросы'}
        </button>
        <div className="flex gap-2 ml-auto">
          {[30, 90, 365].map((d) => (
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
          <HelpCircle className="w-8 h-8 mb-2 text-fg-subtle" />
          <p>Вопросов нет.</p>
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {data!.map((q) => (
            <Card key={q.id} className={cn(
              'p-4', !q.answer && 'border-rose-200 bg-rose-50/30',
            )}>
              <div className="flex items-start gap-3">
                <MessageSquare className="w-5 h-5 text-fg-subtle mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="font-medium text-fg">{q.author || 'Аноним'}</span>
                    <span className="text-xs text-fg-muted">{q.cabinet_name}</span>
                    {!q.answer && (
                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-rose-50 text-rose-700">без ответа</span>
                    )}
                    {q.created_at_ozon && (
                      <span className="text-xs text-fg-subtle ml-auto">
                        {new Date(q.created_at_ozon).toLocaleDateString('ru-RU')}
                      </span>
                    )}
                  </div>
                  {q.product_name && (
                    <div className="text-xs text-fg-muted mt-1 font-mono">{q.offer_id} · {q.product_name}</div>
                  )}
                  <p className="text-sm text-fg mt-2 leading-relaxed">{q.text}</p>
                  {q.answer && (
                    <div className="mt-3 pl-3 border-l-2 border-emerald-300 bg-emerald-50/50 py-2 px-3 rounded-r">
                      <p className="text-xs text-emerald-700 font-semibold mb-1">Ваш ответ:</p>
                      <p className="text-sm text-fg">{q.answer}</p>
                    </div>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
