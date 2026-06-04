/**
 * /alerts/channels — каналы доставки (сводка).
 *
 * Канал = строка в JSONB channels_json у AlertRule.
 * Тут показываем какие каналы используются и насколько.
 */
import { useQuery } from '@tanstack/react-query'
import { Send, MessageCircle, Mail, Globe, Bell } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface Channel {
  kind: string
  enabled_rules_count: number
  total_rules_count: number
}

const CHANNEL_META: Record<string, { label: string; icon: any; help: string }> = {
  in_app: {
    label: 'В приложении',
    icon: Bell,
    help: 'Алерт появится в /alerts. Всегда включён.',
  },
  telegram: {
    label: 'Telegram',
    icon: MessageCircle,
    help: 'Подключите бота в /telegram, затем выберите канал в правилах.',
  },
  email: {
    label: 'Email',
    icon: Mail,
    help: 'Будем слать на email вашего аккаунта. Шаблоны — в /email.',
  },
  webhook: {
    label: 'Webhook',
    icon: Globe,
    help: 'POST на ваш URL. Настройка планируется в /integrations.',
  },
}

export function AlertsChannels() {
  const { data: channels = [] } = useQuery<Channel[]>({
    queryKey: ['alert-channels'],
    queryFn: async () => (await api.get('/alerts/channels')).data,
  })

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
          <Send className="w-6 h-6 text-blue-500" />
          Каналы доставки
        </h1>
        <p className="text-sm text-fg-muted mt-1">
          Куда отправляются алерты. Включение каналов — в настройках каждого правила.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {channels.map((ch) => {
          const meta = CHANNEL_META[ch.kind] || { label: ch.kind, icon: Send, help: '' }
          const Icon = meta.icon
          const active = ch.enabled_rules_count > 0
          return (
            <Card key={ch.kind} className={cn('p-4', active && 'border-emerald-300')}>
              <div className="flex items-start gap-3">
                <Icon className={cn('w-6 h-6 shrink-0',
                  active ? 'text-emerald-600' : 'text-fg-subtle')} />
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <div className="text-base font-semibold text-fg">{meta.label}</div>
                    {active ? (
                      <span className="text-xs px-2 py-0.5 rounded bg-emerald-100 text-emerald-700">
                        активен
                      </span>
                    ) : (
                      <span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                        не используется
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-fg-muted mt-1">{meta.help}</div>
                  <div className="text-xs text-fg-muted mt-2 tabular-nums">
                    Активных правил: <b>{ch.enabled_rules_count}</b> /
                    всего: {ch.total_rules_count}
                  </div>
                </div>
              </div>
            </Card>
          )
        })}
      </div>

      <Card className="p-4 text-sm text-fg-muted">
        <h3 className="text-sm font-semibold text-fg mb-2">Как использовать</h3>
        <ol className="list-decimal pl-5 space-y-1 text-xs">
          <li>Откройте <a href="/alerts/settings" className="text-blue-600 hover:underline">/alerts/settings</a></li>
          <li>В каждом правиле кликните на нужный канал, чтобы включить/выключить</li>
          <li>Для Telegram — сначала привяжите бота в <a href="/telegram" className="text-blue-600 hover:underline">/telegram</a></li>
          <li>Запустите проверки в <a href="/alerts" className="text-blue-600 hover:underline">/alerts</a> → «Запустить проверки»</li>
        </ol>
      </Card>
    </div>
  )
}
