/**
 * AI Drawer — slide-out панель чата справа на любой странице.
 *
 * Open via useAIDrawerStore.open(ctx, question?). На странице автоматически
 * рендерится в AppLayout (фикс справа, 420px). Юзер видит график + AI
 * одновременно, обсуждает данные не теряя контекст экрана.
 *
 * Все вызовы AI идут на main backend /ai/chat (через Render proxy).
 */
import { useEffect, useRef, useState } from 'react'
import {
  Bot, Send, X, Loader2, Sparkles, User as UserIcon, Wrench,
  AlertCircle, Maximize2,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAIDrawerStore } from '@/stores/aiDrawer'
import { cn } from '@/lib/utils'

interface LocalMsg {
  role: 'user' | 'assistant'
  text: string
  tools?: { tool: string }[]
}

type Stage = 'thinking' | 'tools' | 'writing' | null

export function AIDrawer() {
  const { isOpen, context, prefilledQuestion, close } = useAIDrawerStore()
  const navigate = useNavigate()
  const [messages, setMessages] = useState<LocalMsg[]>([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [stage, setStage] = useState<Stage>(null)
  const [streaming, setStreaming] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  // На открытии — заполнить input + сбросить состояние, если контекст изменился
  useEffect(() => {
    if (!isOpen) return
    setMessages([])
    setSessionId(null)
    setInput(prefilledQuestion || '')
  }, [isOpen, context?.source_page, context?.product_id])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  async function sendStream(text: string) {
    setMessages((m) => [...m, { role: 'user', text }, { role: 'assistant', text: '' }])
    setStreaming(true)
    setStage('thinking')

    const cabIds = context?.cabinet_ids?.length
      ? context.cabinet_ids
      : (context?.cabinet_id ? [context.cabinet_id] : [])
    const body = {
      session_id: sessionId,
      text,
      cabinet_scope: cabIds.length
        ? { cabinet_ids: cabIds, active: context?.cabinet_id || cabIds[0] }
        : null,
      attachments: context ? [{
        type: 'chart' as const,
        metrics: context.metrics,
        period: context.period || { from: '', to: '' },
        product_id: context.product_id,
      }] : null,
    }

    try {
      const token = localStorage.getItem('flowoi_token') || localStorage.getItem('token')
      const res = await fetch('/api/v1/ai/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
      })
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // Парсим SSE — события разделены \n\n
        const events = buffer.split('\n\n')
        buffer = events.pop() || ''

        for (const evt of events) {
          const lines = evt.split('\n')
          let event = ''
          let data = ''
          for (const ln of lines) {
            if (ln.startsWith('event: ')) event = ln.slice(7).trim()
            else if (ln.startsWith('data: ')) data = ln.slice(6).trim()
          }
          if (!event) continue
          let payload: any = {}
          try { payload = JSON.parse(data) } catch {}

          if (event === 'stage') {
            setStage(payload.stage)
          } else if (event === 'token') {
            setMessages((m) => {
              const next = [...m]
              const last = next[next.length - 1]
              if (last?.role === 'assistant') {
                next[next.length - 1] = { ...last, text: last.text + (payload.text || '') }
              }
              return next
            })
          } else if (event === 'meta') {
            if (payload.session_id) setSessionId(payload.session_id)
            setMessages((m) => {
              const next = [...m]
              const last = next[next.length - 1]
              if (last?.role === 'assistant') {
                next[next.length - 1] = { ...last, tools: payload.tool_calls }
              }
              return next
            })
          } else if (event === 'error') {
            setMessages((m) => {
              const next = [...m]
              const last = next[next.length - 1]
              if (last?.role === 'assistant') {
                next[next.length - 1] = { ...last, text: `Ошибка: ${payload.message || 'AI недоступен'}` }
              }
              return next
            })
          } else if (event === 'done') {
            setStage(null)
          }
        }
      }
    } catch (e: any) {
      setMessages((m) => {
        const next = [...m]
        const last = next[next.length - 1]
        if (last?.role === 'assistant' && !last.text) {
          next[next.length - 1] = { ...last, text: `Ошибка: ${e?.message || 'AI недоступен'}` }
        }
        return next
      })
    } finally {
      setStreaming(false)
      setStage(null)
    }
  }

  const handleSend = (text: string) => {
    if (!text.trim() || streaming) return
    sendStream(text)
    setInput('')
  }

  if (!isOpen) return null

  return (
    <>
      {/* Затемнение фона на мобильных — на десктопе drawer едет поверх */}
      <div
        className="fixed inset-0 bg-black/20 z-40 lg:hidden"
        onClick={close}
      />
      <div className={cn(
        'fixed top-0 right-0 h-screen w-full lg:w-[440px] bg-bg border-l border-border-subtle',
        'shadow-2xl z-50 flex flex-col',
        'animate-in slide-in-from-right duration-200',
      )}>
        {/* Header */}
        <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <Sparkles className="w-4 h-4 text-violet-500 shrink-0" />
            <div className="min-w-0">
              <div className="text-sm font-semibold text-fg truncate">AI-разбор</div>
              {context?.source_label && (
                <div className="text-[11px] text-fg-muted truncate">
                  {context.source_label}
                  {context.product_id && ' · конкретный SKU'}
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => {
                close()
                navigate('/ai/chat')
              }}
              className="p-1.5 rounded hover:bg-bg-subtle text-fg-muted hover:text-fg"
              title="Открыть полный чат"
            >
              <Maximize2 className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={close}
              className="p-1.5 rounded hover:bg-bg-subtle text-fg-muted hover:text-fg"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Context chip — что AI видит из текущего экрана */}
        {context && (
          <div className="px-4 py-2 bg-violet-50/40 border-b border-border-subtle text-xs text-fg-muted space-y-0.5">
            <div className="text-fg font-medium">
              {context.source_label || context.source_page}
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-0.5">
              {context.product_name && (
                <span>🎯 SKU: <b className="text-fg">{context.product_name}</b></span>
              )}
              {context.cabinet_names && context.cabinet_names.length > 0 && (
                <span>🏪 {context.cabinet_names.join(', ')}</span>
              )}
              {!context.cabinet_names?.length && !context.product_name && (
                <span className="text-fg-subtle">все кабинеты компании</span>
              )}
              {context.period?.from && (
                <span>📅 {context.period.from}…{context.period.to}</span>
              )}
            </div>
            <div className="text-[10px] text-fg-subtle">
              📊 метрики: {context.metrics.slice(0, 4).join(', ')}
              {context.metrics.length > 4 && ` +${context.metrics.length - 4}`}
            </div>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.length === 0 && !streaming && (
            <div className="text-center text-xs text-fg-muted py-8">
              <Sparkles className="w-6 h-6 mx-auto mb-2 text-violet-200" />
              AI видит метрики этого экрана. Задай вопрос или нажми «отправить»
              чтобы получить разбор с гипотезами и числами.
            </div>
          )}
          {messages.map((m, i) => (
            <MessageRow key={i} msg={m} />
          ))}
          {streaming && stage === 'thinking' && (
            <div className="flex gap-2 items-center text-xs text-fg-muted italic">
              <Loader2 className="w-3 h-3 animate-spin" />
              AI считает гипотезы…
            </div>
          )}
          {streaming && stage === 'writing' && (
            <div className="flex gap-2 items-center text-xs text-violet-600 italic">
              <Loader2 className="w-3 h-3 animate-spin" />
              Печатает ответ…
            </div>
          )}
          <div ref={endRef} />
        </div>

        {/* Input */}
        <div className="px-4 py-3 border-t border-border-subtle">
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSend(input)
                }
              }}
              rows={2}
              placeholder="Спроси о том что видишь на экране…"
              className="flex-1 resize-none px-2 py-1.5 border border-border-subtle rounded text-sm bg-bg"
              disabled={streaming}
            />
            <button
              onClick={() => handleSend(input)}
              disabled={!input.trim() || streaming}
              className="px-3 py-1.5 bg-violet-600 text-white rounded text-sm hover:bg-violet-700 disabled:opacity-50 self-end"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </>
  )
}


function MessageRow({ msg }: { msg: LocalMsg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={cn('flex gap-2', isUser && 'flex-row-reverse')}>
      <div className={cn(
        'w-6 h-6 rounded-full flex items-center justify-center shrink-0 text-[10px]',
        isUser ? 'bg-indigo-100 text-indigo-700' : 'bg-violet-100 text-violet-700',
      )}>
        {isUser ? <UserIcon className="w-3 h-3" /> : <Bot className="w-3 h-3" />}
      </div>
      <div className={cn(
        'flex-1 max-w-[88%] rounded px-2.5 py-1.5 text-xs leading-relaxed whitespace-pre-wrap',
        isUser ? 'bg-indigo-50 text-indigo-900' : 'bg-bg-subtle text-fg',
      )}>
        {msg.text}
        {msg.tools && msg.tools.length > 0 && (
          <div className="mt-1.5 pt-1.5 border-t border-border-subtle text-[10px] text-fg-muted flex items-center gap-1">
            <Wrench className="w-2.5 h-2.5" />
            {msg.tools.map(t => t.tool).join(', ')}
          </div>
        )}
      </div>
    </div>
  )
}
