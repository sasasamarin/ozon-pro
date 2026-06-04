/**
 * /integrations — интеграции с внешними системами.
 *
 * Статусы:
 *   - Ozon: подключено (через /cabinets)
 *   - остальные: planned / coming-soon
 */
import { useQuery } from '@tanstack/react-query'
import {
  Plug, Store, Database, FileSpreadsheet, Webhook,
  CheckCircle2, Clock, ExternalLink,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface Cabinet {
  id: string
  account_name: string
}

type Status = 'connected' | 'available' | 'planned' | 'beta'

const INTEGRATIONS: Array<{
  kind: string
  label: string
  desc: string
  icon: any
  status: Status
  link?: string
  external?: string
}> = [
  {
    kind: 'ozon',
    label: 'Ozon (Seller + Performance)',
    desc: 'Магазины Ozon — продажи, склады, реклама, отзывы.',
    icon: Store, status: 'connected', link: '/cabinets',
  },
  {
    kind: 'tg',
    label: 'Telegram бот',
    desc: 'Алерты и сводки в чат.',
    icon: Webhook, status: 'beta', link: '/telegram',
  },
  {
    kind: 'wb',
    label: 'Wildberries',
    desc: 'Второй маркетплейс. В roadmap, дайте знать если нужно срочно.',
    icon: Store, status: 'planned',
  },
  {
    kind: '1c',
    label: '1С (выгрузка проводок)',
    desc: 'Импорт приёмок, продаж, остатков из 1С.',
    icon: Database, status: 'planned',
  },
  {
    kind: 'bank',
    label: 'Банк-выписки',
    desc: 'Тинькофф / Сбер — для точного cashflow.',
    icon: Database, status: 'planned',
  },
  {
    kind: 'sheets',
    label: 'Google Sheets',
    desc: 'Экспорт отчётов на регулярной основе.',
    icon: FileSpreadsheet, status: 'planned',
  },
  {
    kind: 'webhook',
    label: 'Webhook (свой URL)',
    desc: 'POST на ваш сервер при срабатывании алертов.',
    icon: Webhook, status: 'planned',
  },
]

const STATUS_META: Record<Status, { label: string; tone: string }> = {
  connected: { label: 'подключено', tone: 'bg-emerald-100 text-emerald-700' },
  available: { label: 'доступно', tone: 'bg-blue-100 text-blue-700' },
  beta: { label: 'beta', tone: 'bg-purple-100 text-purple-700' },
  planned: { label: 'в roadmap', tone: 'bg-slate-100 text-slate-600' },
}

export function Integrations() {
  const { data: cabinets = [] } = useQuery<Cabinet[]>({
    queryKey: ['cabinets-min'],
    queryFn: async () => (await api.get('/ozon-accounts/')).data,
  })

  return (
    <div className="space-y-5 max-w-4xl">
      <div>
        <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
          <Plug className="w-6 h-6 text-blue-500" />
          Интеграции
        </h1>
        <p className="text-sm text-fg-muted mt-1">
          Внешние системы, с которыми Flowoi умеет работать.
          Что-то нужно срочно — напишите в поддержку.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {INTEGRATIONS.map((i) => {
          const Icon = i.icon
          const status = STATUS_META[i.status]
          const isOzon = i.kind === 'ozon'
          return (
            <Card key={i.kind} className={cn('p-4',
              i.status === 'connected' && 'border-emerald-300')}>
              <div className="flex items-start gap-3">
                <Icon className={cn('w-6 h-6 shrink-0',
                  i.status === 'connected' ? 'text-emerald-600' :
                  i.status === 'beta' ? 'text-purple-600' :
                  'text-fg-subtle')} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <div className="text-sm font-semibold text-fg">{i.label}</div>
                    <span className={cn('text-[10px] px-2 py-0.5 rounded inline-flex items-center gap-1',
                      status.tone)}>
                      {i.status === 'connected' && <CheckCircle2 className="w-3 h-3" />}
                      {i.status === 'planned' && <Clock className="w-3 h-3" />}
                      {status.label}
                    </span>
                  </div>
                  <div className="text-xs text-fg-muted mb-2">{i.desc}</div>
                  {isOzon && (
                    <div className="text-[11px] text-fg-muted">
                      Подключено магазинов: <b className="text-fg">{cabinets.length}</b>
                    </div>
                  )}
                  <div className="mt-3 flex gap-2">
                    {i.link && (
                      <Button variant="secondary" onClick={() => window.location.href = i.link!}
                              className="text-xs px-2 py-1">
                        Открыть
                      </Button>
                    )}
                    {i.external && (
                      <Button variant="ghost"
                              onClick={() => window.open(i.external, '_blank')}
                              className="text-xs px-2 py-1 inline-flex items-center gap-1">
                        Документация <ExternalLink className="w-3 h-3" />
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            </Card>
          )
        })}
      </div>

      <Card className="p-4 bg-blue-50/30 border-blue-200 text-sm">
        <div className="font-semibold text-fg mb-1">Нужна интеграция, которой здесь нет?</div>
        <div className="text-fg-muted">
          Напишите{' '}
          <a href="https://t.me/codexa_support" target="_blank" rel="noopener"
             className="text-blue-600 hover:underline">@codexa_support</a>
          {' '}— приоритизируем по спросу.
        </div>
      </Card>
    </div>
  )
}
