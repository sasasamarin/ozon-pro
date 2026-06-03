/**
 * AI-чат (Phase 1 — FLOWOI_AI_TZ §5).
 *
 * Источник: новые endpoints /ai/chat, /ai/sessions, /ai/sessions/:id.
 * Фишки:
 *  - переключение кабинетов внутри сессии (cabinet_scope)
 *  - прикрепление графиков (контекст: метрики/период/product_id), не картинка
 *  - история чатов
 *  - tool_calls log на каждый ответ (видно какие данные LLM забирал)
 */
import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Sparkles, Send, Bot, User as UserIcon, Plus, Trash2,
  AlertCircle, Loader2, Wrench, Building2, Paperclip, X,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api } from '@/lib/api'
import { useCabinetStore } from '@/stores/cabinet'
import { cn } from '@/lib/utils'

interface Session {
  id: string
  title: string | null
  cabinet_scope: { cabinet_ids?: string[]; active?: string } | null
  created_at: string
  updated_at: string
}
interface Message {
  id: string
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: string | null
  tool_calls: unknown[] | null
  attachments: unknown[] | null
  model_used: string | null
  created_at: string
}
interface ChatResp {
  session_id: string
  title: string | null
  answer: string
  model: string
  input_tokens: number
  output_tokens: number
  iterations: number
  tool_calls: { tool: string; args: Record<string, unknown>; result_preview: string }[]
  error: boolean
}
interface StatusResp {
  configured: boolean
  model: string
  provider: string
}
interface Cabinet { id: string; name: string }
interface ChartAttachment {
  type: 'chart'
  metrics: string[]
  period: { from: string; to: string }
  product_id?: string
}

const STARTERS = [
  'Почему упала выручка вчера?',
  'Покажи P&L за 30 дней (оперативный контур)',
  'Какие SKU кандидаты на вывод? (keep_or_drop)',
  'У какого товара лучшая эластичность? Стоит поднять цену?',
  'Что узким местом в воронке Жирафа?',
  'Прогноз продаж Капучинатора на 3 месяца',
]

export function AIChat() {
  const qc = useQueryClient()
  const { selectedCabinetIds } = useCabinetStore()

  const [activeId, setActiveId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [pendingMsg, setPendingMsg] = useState<string | null>(null)
  const [lastResp, setLastResp] = useState<ChatResp | null>(null)
  const [attachments, setAttachments] = useState<ChartAttachment[]>([])
  const endRef = useRef<HTMLDivElement>(null)

  // Список кабинетов компании
  const { data: cabinets = [] } = useQuery<Cabinet[]>({
    queryKey: ['cabinets-for-ai'],
    queryFn: async () => {
      const r = await api.get('/ozon-accounts')
      return r.data
    },
  })

  const { data: status } = useQuery<StatusResp>({
    queryKey: ['ai-v2-status'],
    queryFn: async () => (await api.get('/ai/v2/status')).data,
  })

  const { data: sessions = [] } = useQuery<Session[]>({
    queryKey: ['ai-sessions'],
    queryFn: async () => (await api.get('/ai/sessions')).data,
  })

  const { data: messages = [] } = useQuery<Message[]>({
    queryKey: ['ai-session-messages', activeId],
    queryFn: async () => (await api.get(`/ai/sessions/${activeId}`)).data,
    enabled: !!activeId,
  })

  const activeSession = sessions.find(s => s.id === activeId)
  const scopeCabinets = activeSession?.cabinet_scope?.cabinet_ids
    || selectedCabinetIds
    || []
  const activeCab = activeSession?.cabinet_scope?.active
    || (selectedCabinetIds[0] ?? null)

  const send = useMutation<ChatResp, Error, string>({
    mutationFn: async (text: string) => {
      setPendingMsg(text)
      const body = {
        session_id: activeId,
        text,
        cabinet_scope: scopeCabinets.length > 0 ? {
          cabinet_ids: scopeCabinets,
          active: activeCab,
        } : null,
        attachments: attachments.length > 0 ? attachments : null,
      }
      const r = await api.post('/ai/chat', body)
      return r.data
    },
    onSuccess: (data) => {
      setPendingMsg(null)
      setLastResp(data)
      setAttachments([])
      if (!activeId) setActiveId(data.session_id)
      qc.invalidateQueries({ queryKey: ['ai-sessions'] })
      qc.invalidateQueries({ queryKey: ['ai-session-messages', data.session_id] })
    },
    onError: () => setPendingMsg(null),
  })

  const removeSession = useMutation({
    mutationFn: async (id: string) => api.delete(`/ai/sessions/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ai-sessions'] })
      setActiveId(null)
    },
  })

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, send.isPending, pendingMsg])

  const handleSend = (text: string) => {
    if (!text.trim() || send.isPending) return
    send.mutate(text)
    setInput('')
  }

  const setActiveCabinet = (cabId: string | null) => {
    if (!activeId) return
    const scope: { cabinet_ids?: string[]; active?: string } = {
      cabinet_ids: cabId ? [cabId] : selectedCabinetIds,
    }
    if (cabId) scope.active = cabId
    // Оптимистично обновим UI; реальный persist — на следующий send (orchestrator сохранит)
    qc.setQueryData<Session[]>(['ai-sessions'], (old) =>
      (old || []).map(s => s.id === activeId ? { ...s, cabinet_scope: scope } : s)
    )
  }

  return (
    <div className="flex flex-col gap-4 h-[calc(100vh-120px)]">
      <Header status={status} />

      {status && !status.configured && (
        <Card className="p-3 bg-amber-50 border-amber-200 text-sm text-amber-900 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            <strong>OPENAI_API_KEY не задан в env бэкенда.</strong>{' '}
            Добавь в Render Environment и перезапусти сервис. Ключ только на бэкенде, фронт его не видит.
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 flex-1 min-h-0">
        {/* Sessions panel */}
        <Card className="lg:col-span-1 p-3 flex flex-col min-h-0">
          <button
            onClick={() => { setActiveId(null); setInput(''); setAttachments([]) }}
            className="w-full px-3 py-2 mb-3 border border-dashed border-border-subtle rounded text-sm text-fg-muted hover:text-fg hover:bg-bg-subtle flex items-center justify-center gap-1.5"
          >
            <Plus className="w-3.5 h-3.5" /> Новый чат
          </button>
          <div className="flex-1 overflow-y-auto -mx-1 px-1">
            {sessions.length === 0 && (
              <p className="text-xs text-fg-muted px-2 py-1">Нет сессий</p>
            )}
            {sessions.map((s) => (
              <div
                key={s.id}
                onClick={() => setActiveId(s.id)}
                className={cn(
                  'group flex items-center gap-1 px-2 py-1.5 rounded mb-0.5 cursor-pointer',
                  activeId === s.id ? 'bg-violet-50' : 'hover:bg-bg-subtle',
                )}
              >
                <Bot className="w-3.5 h-3.5 text-fg-muted shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-fg truncate">{s.title || 'Без названия'}</div>
                  {s.cabinet_scope?.cabinet_ids && s.cabinet_scope.cabinet_ids.length > 0 && (
                    <div className="text-[10px] text-fg-muted truncate">
                      {s.cabinet_scope.cabinet_ids.length} каб.
                    </div>
                  )}
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); if (confirm('Удалить?')) removeSession.mutate(s.id) }}
                  className="opacity-0 group-hover:opacity-100 text-fg-muted hover:text-rose-600"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        </Card>

        {/* Chat panel */}
        <Card className="lg:col-span-3 flex flex-col min-h-0">
          {/* Cabinet selector strip */}
          {activeId && cabinets.length > 0 && (
            <div className="px-4 py-2 border-b border-border-subtle flex items-center gap-2 text-xs">
              <Building2 className="w-3.5 h-3.5 text-fg-muted" />
              <span className="text-fg-muted">Активный кабинет:</span>
              <select
                value={activeCab || ''}
                onChange={(e) => setActiveCabinet(e.target.value || null)}
                className="px-2 py-0.5 border border-border-subtle rounded bg-bg text-fg"
              >
                <option value="">— все —</option>
                {cabinets.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <span className="text-fg-muted ml-2">— переключение не теряет историю.</span>
            </div>
          )}

          {!activeId && messages.length === 0 && !pendingMsg && (
            <div className="flex-1 overflow-y-auto p-5 flex flex-col items-center justify-center gap-4">
              <Sparkles className="w-12 h-12 text-violet-200" />
              <p className="text-fg-muted text-sm">Задай вопрос или выбери шаблон</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-w-2xl w-full">
                {STARTERS.map(p => (
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

          {(activeId || pendingMsg) && (
            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {messages.map(m => (
                <Bubble key={m.id} role={m.role} content={m.content || ''}
                       hasAttachments={!!m.attachments?.length}
                       hasToolCalls={!!m.tool_calls?.length && m.role === 'assistant'} />
              ))}
              {pendingMsg && <Bubble role="user" content={pendingMsg} />}
              {send.isPending && (
                <div className="flex gap-3 items-center">
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
                  Использовал tools: {lastResp.tool_calls.map(t => t.tool).join(', ')}
                  <span className="ml-2">· {lastResp.input_tokens}→{lastResp.output_tokens} токенов</span>
                </div>
              )}
              <div ref={endRef} />
            </div>
          )}

          {/* Attachments preview */}
          {attachments.length > 0 && (
            <div className="px-5 pt-2 flex flex-wrap gap-2">
              {attachments.map((a, i) => (
                <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs">
                  <Paperclip className="w-3 h-3" />
                  {a.type}: {a.metrics.join(', ')} · {a.period.from}…{a.period.to}
                  <button onClick={() => setAttachments(prev => prev.filter((_, j) => j !== i))}>
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          )}

          {/* Input */}
          <div className="px-5 py-3 border-t border-border-subtle flex gap-2">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend(input)}
              placeholder={status?.configured ? "Спроси про бизнес — данные приедут из tools" : "OPENAI_API_KEY не настроен"}
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


function Header({ status }: { status: StatusResp | undefined }) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-violet-500" />
          AI-чат
        </h1>
        <p className="text-sm text-fg-muted mt-1">
          Естественный язык, данные через tools. Цифры — только из БД/моделей, не из генерации.
        </p>
      </div>
      {status && (
        <div className="text-xs">
          {status.configured ? (
            <span className="px-2 py-1 bg-emerald-50 text-emerald-700 rounded">
              {status.provider} · {status.model}
            </span>
          ) : (
            <span className="px-2 py-1 bg-amber-50 text-amber-700 rounded">
              Ключ не задан
            </span>
          )}
        </div>
      )}
    </div>
  )
}


function Bubble({ role, content, hasAttachments, hasToolCalls }: {
  role: string
  content: string
  hasAttachments?: boolean
  hasToolCalls?: boolean
}) {
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
        {hasAttachments && (
          <div className="text-[11px] text-fg-muted mt-1 italic">📎 контекст графика приложен</div>
        )}
        {hasToolCalls && (
          <div className="text-[11px] text-fg-muted mt-1 italic">🔧 tools использованы</div>
        )}
      </div>
    </div>
  )
}
