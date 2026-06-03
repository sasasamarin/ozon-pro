/**
 * AI-чат с tool-calling. Использует /api/v1/ai/chats/*.
 * LLM ходит в наши tools (revenue/stockouts/funnel/seasonality/...) и отвечает
 * на их основе. Список чатов слева, история — справа.
 */
import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Sparkles, Send, Bot, User as UserIcon, Plus, Trash2,
  AlertCircle, Loader2, Wrench,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface ChatItem {
  id: string
  title: string | null
  created_at: string
  updated_at: string
}
interface MessageItem {
  id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  model_used: string | null
  created_at: string
}
interface ToolCall {
  tool: string
  args: Record<string, unknown>
  result_preview: string
}
interface SendResp {
  chat_id: string
  title: string | null
  answer: string
  model: string
  input_tokens: number
  output_tokens: number
  iterations: number
  tool_calls: ToolCall[]
  error: boolean
}
interface StatusResp {
  configured: boolean
  via_proxy: boolean
  default_model: string
}

const STARTER_PROMPTS = [
  'Какие товары горят? Где грозит стокаут?',
  'Дай сводку выручки за 30 дней',
  'Топ-5 SKU по марже',
  'Какие товары больше всего возвращают?',
  'У Жирафа есть сезонность?',
  'Покажи P&L за последний месяц',
]

export function AIChat() {
  const qc = useQueryClient()
  const [activeChatId, setActiveChatId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [pendingUserMsg, setPendingUserMsg] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  const { data: status } = useQuery<StatusResp>({
    queryKey: ['ai-status'],
    queryFn: async () => (await api.get('/ai/status')).data,
  })

  const { data: chats = [] } = useQuery<ChatItem[]>({
    queryKey: ['ai-chats'],
    queryFn: async () => (await api.get('/ai/chats')).data,
  })

  const { data: messages = [], isLoading: msgsLoading } = useQuery<MessageItem[]>({
    queryKey: ['ai-messages', activeChatId],
    queryFn: async () => (await api.get(`/ai/chats/${activeChatId}/messages`)).data,
    enabled: !!activeChatId,
  })

  const [lastResp, setLastResp] = useState<SendResp | null>(null)
  const send = useMutation<SendResp, Error, string>({
    mutationFn: async (text: string) => {
      setPendingUserMsg(text)
      const body = {
        chat_id: activeChatId, text,
        context_page: 'ai-chat',
      }
      const r = await api.post('/ai/chats/messages', body)
      return r.data
    },
    onSuccess: (data) => {
      setPendingUserMsg(null)
      setLastResp(data)
      if (!activeChatId) setActiveChatId(data.chat_id)
      qc.invalidateQueries({ queryKey: ['ai-chats'] })
      qc.invalidateQueries({ queryKey: ['ai-messages', data.chat_id] })
    },
    onError: () => {
      setPendingUserMsg(null)
    },
  })

  const removeChat = useMutation({
    mutationFn: async (id: string) => api.delete(`/ai/chats/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ai-chats'] })
      setActiveChatId(null)
    },
  })

  // Auto-scroll к низу при новых сообщениях
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, send.isPending, pendingUserMsg])

  const handleSend = (text: string) => {
    if (!text.trim() || send.isPending) return
    send.mutate(text)
    setInput('')
  }

  const startNewChat = () => {
    setActiveChatId(null)
    setInput('')
  }

  return (
    <div className="flex flex-col gap-4 h-[calc(100vh-120px)]">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-violet-500" />
            AI-помощник
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            Ходит по твоим данным через tools. Спроси что угодно — выручка, остатки,
            маржа, сезонность, P&L.
          </p>
        </div>
        {status && (
          <div className="text-xs">
            {status.configured ? (
              <span className="px-2 py-1 bg-emerald-50 text-emerald-700 rounded">
                AI готов · {status.default_model.replace('claude-', '')}
                {status.via_proxy && ' · via proxy'}
              </span>
            ) : (
              <span className="px-2 py-1 bg-amber-50 text-amber-700 rounded">
                AI не настроен
              </span>
            )}
          </div>
        )}
      </div>

      {status && !status.configured && (
        <Card className="p-3 bg-amber-50 border-amber-200 text-sm text-amber-900 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            <strong>AI не настроен.</strong> Добавь в <code>.env</code> бэкенда
            <code className="mx-1 px-1 bg-white rounded">AI_PROXY_URL</code> (Render-прокси)
            и <code className="mx-1 px-1 bg-white rounded">AI_PROXY_TOKEN</code>, перезапусти контейнер.
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 flex-1 min-h-0">
        {/* Левая колонка: список чатов */}
        <Card className="lg:col-span-1 p-3 flex flex-col min-h-0">
          <button
            onClick={startNewChat}
            className="w-full px-3 py-2 mb-3 border border-dashed border-border-subtle rounded text-sm
                       text-fg-muted hover:text-fg hover:bg-bg-subtle flex items-center justify-center gap-1.5"
          >
            <Plus className="w-3.5 h-3.5" /> Новый чат
          </button>
          <div className="flex-1 overflow-y-auto -mx-1 px-1">
            {chats.length === 0 && (
              <p className="text-xs text-fg-muted px-2 py-1">Чатов пока нет</p>
            )}
            {chats.map((c) => (
              <div
                key={c.id}
                className={cn(
                  'group flex items-center gap-1 px-2 py-1.5 rounded mb-0.5 cursor-pointer',
                  activeChatId === c.id ? 'bg-violet-50' : 'hover:bg-bg-subtle',
                )}
                onClick={() => setActiveChatId(c.id)}
              >
                <Bot className="w-3.5 h-3.5 text-fg-muted shrink-0" />
                <span className="flex-1 text-xs text-fg truncate">
                  {c.title || 'Без названия'}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    if (confirm('Удалить чат?')) removeChat.mutate(c.id)
                  }}
                  className="opacity-0 group-hover:opacity-100 text-fg-muted hover:text-rose-600"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        </Card>

        {/* Правая колонка: чат */}
        <Card className="lg:col-span-3 flex flex-col min-h-0">
          {!activeChatId && messages.length === 0 && !pendingUserMsg && (
            <div className="flex-1 overflow-y-auto p-5 flex flex-col items-center justify-center gap-4">
              <Sparkles className="w-12 h-12 text-violet-200" />
              <p className="text-fg-muted text-sm">Задай вопрос или выбери шаблон</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-w-2xl w-full">
                {STARTER_PROMPTS.map((p) => (
                  <button
                    key={p}
                    onClick={() => handleSend(p)}
                    className="text-left text-xs text-fg-muted hover:text-fg hover:bg-bg-subtle border border-border-subtle px-3 py-2 rounded-md"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}

          {(activeChatId || pendingUserMsg) && (
            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {msgsLoading && <Loader2 className="w-4 h-4 animate-spin text-fg-muted mx-auto" />}
              {messages.map((m) => (
                <MessageBubble key={m.id} role={m.role} content={m.content} />
              ))}
              {pendingUserMsg && (
                <MessageBubble role="user" content={pendingUserMsg} />
              )}
              {send.isPending && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-violet-100 text-violet-700 flex items-center justify-center shrink-0">
                    <Bot className="w-4 h-4" />
                  </div>
                  <div className="text-sm text-fg-muted italic flex items-center gap-2">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    AI думает…
                  </div>
                </div>
              )}
              {lastResp && lastResp.tool_calls.length > 0 && (
                <div className="text-xs text-fg-muted bg-bg-subtle/40 rounded p-2 border border-border-subtle">
                  <Wrench className="w-3 h-3 inline mr-1" />
                  Вызвано инструментов: {lastResp.tool_calls.map(t => t.tool).join(', ')}
                  <span className="ml-2">· {lastResp.input_tokens}→{lastResp.output_tokens} токенов</span>
                </div>
              )}
              <div ref={endRef} />
            </div>
          )}

          <div className="px-5 py-3 border-t border-border-subtle flex gap-2">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend(input)}
              placeholder={status?.configured ? "Спроси что-нибудь" : "AI не настроен — см. баннер выше"}
              disabled={!status?.configured || send.isPending}
              className="flex-1"
            />
            <Button
              onClick={() => handleSend(input)}
              disabled={!input.trim() || !status?.configured || send.isPending}
            >
              <Send className="w-4 h-4" />
            </Button>
          </div>
        </Card>
      </div>
    </div>
  )
}


function MessageBubble({ role, content }: { role: string; content: string }) {
  const isUser = role === 'user'
  return (
    <div className={cn('flex gap-3', isUser && 'flex-row-reverse')}>
      <div className={cn(
        'w-8 h-8 rounded-full flex items-center justify-center shrink-0',
        isUser ? 'bg-indigo-100 text-indigo-700' : 'bg-violet-100 text-violet-700',
      )}>
        {isUser ? <UserIcon className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>
      <div className={cn(
        'flex-1 max-w-[80%] rounded-lg px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap',
        isUser ? 'bg-indigo-50 text-indigo-900' : 'bg-bg-subtle text-fg',
      )}>
        {content}
      </div>
    </div>
  )
}
