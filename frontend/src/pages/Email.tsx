import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Mail, Loader2, FileText } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface EmailLog {
  id: string
  to_email: string
  subject: string | null
  template: string | null
  status: string
  error_message: string | null
  sent_at: string | null
  created_at: string
}

interface TemplateRow {
  key: string
  label: string
}

const STATUS_META: Record<string, { label: string; cls: string }> = {
  queued: { label: 'В очереди', cls: 'bg-amber-50 text-amber-700' },
  sent: { label: 'Отправлено', cls: 'bg-emerald-50 text-emerald-700' },
  failed: { label: 'Ошибка', cls: 'bg-rose-50 text-rose-700' },
}

export function Email() {
  const [status, setStatus] = useState('')

  const { data: templates } = useQuery<TemplateRow[]>({
    queryKey: ['email', 'templates'],
    queryFn: async () => (await api.get('/email/templates')).data,
  })

  const { data: logs, isLoading } = useQuery<EmailLog[]>({
    queryKey: ['email', 'log', status],
    queryFn: async () => {
      const q = status ? `?status=${status}` : ''
      return (await api.get(`/email/log${q}`)).data
    },
  })

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Email</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          {templates?.length ?? 0} шаблонов · {logs?.length ?? 0} писем
        </p>
      </div>

      {/* Templates */}
      <Card className="p-5">
        <h2 className="text-base font-semibold text-fg flex items-center gap-2 mb-3">
          <FileText className="w-4 h-4 text-fg-muted" />
          Доступные шаблоны
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-2">
          {(templates || []).map((t) => (
            <div key={t.key} className="px-3 py-2 rounded-md border border-border-subtle bg-bg-subtle/30">
              <div className="text-sm font-medium text-fg">{t.label}</div>
              <div className="text-[10px] text-fg-subtle font-mono mt-0.5">{t.key}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* Logs */}
      <div className="flex gap-2">
        {['', 'queued', 'sent', 'failed'].map((s) => (
          <button key={s} onClick={() => setStatus(s)} className={cn(
            'px-3 py-1.5 rounded-md text-sm border transition-colors',
            status === s ? 'border-fg bg-fg text-bg' : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
          )}>
            {s === '' ? 'Все' : STATUS_META[s]?.label}
          </button>
        ))}
      </div>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 flex justify-center"><Loader2 className="w-5 h-5 animate-spin" /></div>
        ) : (logs?.length ?? 0) === 0 ? (
          <div className="py-12 flex flex-col items-center text-fg-muted text-sm">
            <Mail className="w-8 h-8 mb-2 text-fg-subtle" />
            <p>Писем нет.</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-bg-subtle/50 border-b border-border-subtle">
              <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                <th className="py-2.5 px-4 font-medium">когда</th>
                <th className="py-2.5 px-4 font-medium">шаблон</th>
                <th className="py-2.5 px-4 font-medium">кому</th>
                <th className="py-2.5 px-4 font-medium">тема</th>
                <th className="py-2.5 px-4 font-medium">статус</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {logs!.map((e) => {
                const meta = STATUS_META[e.status] || { label: e.status, cls: '' }
                return (
                  <tr key={e.id} className="hover:bg-bg-subtle/40">
                    <td className="py-2.5 px-4 text-fg-muted text-xs tabular-nums">
                      {new Date(e.created_at).toLocaleString('ru-RU')}
                    </td>
                    <td className="py-2.5 px-4 text-xs font-mono">{e.template || '—'}</td>
                    <td className="py-2.5 px-4 font-mono text-xs">{e.to_email}</td>
                    <td className="py-2.5 px-4 text-fg truncate max-w-[300px]">{e.subject || '—'}</td>
                    <td className="py-2.5 px-4">
                      <span className={cn('text-xs font-medium px-1.5 py-0.5 rounded', meta.cls)}>{meta.label}</span>
                      {e.error_message && <div className="text-[10px] text-rose-700 mt-1">{e.error_message}</div>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}
