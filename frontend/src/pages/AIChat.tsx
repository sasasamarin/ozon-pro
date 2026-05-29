import { useState } from 'react'
import { Sparkles, Send, Bot, User as UserIcon, Lock } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { cn } from '@/lib/utils'

interface Message {
  role: 'user' | 'assistant'
  text: string
}

const STARTER_PROMPTS = [
  'Какие товары горят? Где грозит стокаут?',
  'У какого SKU лучшая маржа?',
  'Дай сводку выручки за месяц',
  'Какие категории дают больше всего прибыли?',
  'Что показывает воронка по Жирафу?',
]

const DEMO_RESPONSES: Record<string, string> = {
  стокаут:
    'За последние 30 дней горят 4 SKU: 600х450grafit (0 шт), Crema Viva (1 шт), Grano (0 шт), GlattFix (1 шт). Все в категории «нет данных по доставке Москва». Рекомендую закупить — детали в /procurement/forecast.',
  маржа:
    'Топ-3 по марже: Жираф (~70% валовой), WandTech (~65%), Crema Viva (~58%). Полная разбивка в /products/categories.',
  выручка:
    'Выручка за 30 дней: 14.4М ₽ (3 кабинета). home лидирует — 5.8М. По дням см. /dashboard.',
  категори:
    'Все 81 SKU в «(без категории)» — Ozon не отдаёт category_name через /v3/product/info/list. Чтобы видеть категории — заполни их вручную или подключи Premium для расширенного синка.',
  воронк:
    'Воронка Жирафа (28 дней): 91k показов → 1.5k в корзину (1.6%) → 421 заказов (28%) → 371 доставлено (88%). Сквозная конверсия 0.41% — стандартно для бытовой техники.',
}

export function AIChat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      text:
        'Я Flowoi AI. Пока я работаю в demo-режиме на пред-заданных ответах. Полная версия с подключением Claude/GPT и доступом к твоим данным появится в Premium Plus. Попробуй один из вопросов слева.',
    },
  ])
  const [input, setInput] = useState('')

  const send = (text: string) => {
    if (!text.trim()) return
    const lower = text.toLowerCase()
    const matched =
      Object.entries(DEMO_RESPONSES).find(([k]) => lower.includes(k))?.[1] ??
      'Я ещё учусь. В demo-режиме отвечаю только на вопросы про стокауты, маржу, выручку, категории и воронку. Полная AI-копилот — Premium Plus.'
    setMessages((m) => [
      ...m,
      { role: 'user', text },
      { role: 'assistant', text: matched },
    ])
    setInput('')
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <div className="inline-flex items-center gap-2 rounded-full border border-border-subtle bg-bg-subtle/60 px-2.5 py-1 text-xs font-medium text-fg-muted">
          <Sparkles className="w-3 h-3" />
          Beta · ИИ-помощник
        </div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight mt-3">AI-чат</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          Задай вопрос про свой бизнес — AI вытащит ответ из твоих данных.
        </p>
      </div>

      <Card className="p-4 bg-amber-50/40 border-amber-200 flex items-start gap-3">
        <Lock className="w-5 h-5 text-amber-700 mt-0.5 shrink-0" />
        <div className="text-sm text-amber-900/90">
          <strong>Demo-режим.</strong> Полный AI с доступом к выручке, остаткам, прогнозам — в плане Premium Plus.
          Сейчас отвечает на ~5 типов вопросов из примера.
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <Card className="lg:col-span-1 p-4">
          <h3 className="text-sm font-semibold text-fg mb-3">Попробуй спросить:</h3>
          <ul className="flex flex-col gap-2">
            {STARTER_PROMPTS.map((p) => (
              <li key={p}>
                <button
                  onClick={() => send(p)}
                  className="text-left text-xs text-fg-muted hover:text-fg hover:bg-bg-subtle px-2 py-1.5 rounded-md w-full"
                >
                  {p}
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="lg:col-span-3 flex flex-col" style={{ minHeight: '500px' }}>
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {messages.map((m, i) => (
              <div key={i} className={cn('flex gap-3', m.role === 'user' && 'flex-row-reverse')}>
                <div className={cn(
                  'w-8 h-8 rounded-full flex items-center justify-center shrink-0',
                  m.role === 'user' ? 'bg-indigo-100 text-indigo-700' : 'bg-violet-100 text-violet-700',
                )}>
                  {m.role === 'user' ? <UserIcon className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                </div>
                <div className={cn(
                  'flex-1 max-w-[80%] rounded-lg px-3 py-2 text-sm leading-relaxed',
                  m.role === 'user' ? 'bg-indigo-50 text-indigo-900' : 'bg-bg-subtle text-fg',
                )}>
                  {m.text}
                </div>
              </div>
            ))}
          </div>
          <div className="px-5 py-3 border-t border-border-subtle flex gap-2">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && send(input)}
              placeholder="Спроси что-нибудь про бизнес"
              className="flex-1"
            />
            <Button onClick={() => send(input)} disabled={!input.trim()}>
              <Send className="w-4 h-4" />
            </Button>
          </div>
        </Card>
      </div>
    </div>
  )
}
