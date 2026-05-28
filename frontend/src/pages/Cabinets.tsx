import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Plus, Store, ArrowUpRight, AlertCircle, Megaphone } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { HelpHint } from '@/components/ui/HelpHint'
import { api } from '@/lib/api'
import { formatRelativeTime, cn } from '@/lib/utils'
import { PREMIUM_TIER_OPTIONS, type PremiumTier } from '@/components/PremiumTierSelect'
import { getErrorMessage } from '@/lib/errors'
import type { OzonAccountSummary } from '@/stores/cabinet'

const TIER_BY_VALUE = Object.fromEntries(
  PREMIUM_TIER_OPTIONS.map((o) => [o.value, o])
) as Record<PremiumTier, (typeof PREMIUM_TIER_OPTIONS)[number]>

const STATUS_LABEL: Record<string, { label: string; tone: 'success' | 'error' | 'muted' }> = {
  active: { label: 'Активен', tone: 'success' },
  syncing: { label: 'Синхронизация', tone: 'muted' },
  error: { label: 'Ошибка', tone: 'error' },
  inactive: { label: 'Отключён', tone: 'muted' },
}

export function Cabinets() {
  const { data, isLoading } = useQuery<OzonAccountSummary[]>({
    queryKey: ['ozon-accounts'],
    queryFn: async () => {
      const res = await api.get('/ozon-accounts/')
      return res.data
    },
    // Карточки чувствительны к свежему статусу — синки бегут параллельно,
    // не доверяем stale-кэшу.
    refetchOnMount: 'always',
    refetchOnWindowFocus: true,
    staleTime: 0,
  })

  const cabinets = data || []

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-3xl font-semibold text-fg tracking-tight">Кабинеты Ozon</h1>
            <HelpHint text="Подключенные магазины Ozon, по одной карточке на каждый. Клик → редактирование (ключи, тариф, удаление). Статус «Активен» = последний sync прошёл; «Ошибка» = есть проблема с Ozon API. Бэйдж «Реклама» = подключён Performance API (рекламная статистика тянется)." />
          </div>
          <p className="text-sm text-fg-muted mt-1.5">
            {cabinets.length > 0
              ? `Подключено кабинетов: ${cabinets.length}`
              : 'Подключи свой первый кабинет'}
          </p>
        </div>
        <Link to="/cabinets/new">
          <Button>
            <Plus className="w-4 h-4" />
            Добавить кабинет
          </Button>
        </Link>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {[1, 2].map((i) => (
            <Card key={i} className="p-6 animate-pulse">
              <div className="h-5 w-32 bg-bg-subtle rounded mb-2" />
              <div className="h-4 w-48 bg-bg-subtle rounded" />
            </Card>
          ))}
        </div>
      ) : cabinets.length === 0 ? (
        <Card className="p-12 flex flex-col items-center text-center">
          <div className="w-14 h-14 rounded-full bg-bg-subtle flex items-center justify-center mb-4">
            <Store className="w-6 h-6 text-fg-muted" />
          </div>
          <h3 className="text-lg font-semibold text-fg">Кабинеты не подключены</h3>
          <p className="text-sm text-fg-muted mt-1.5 max-w-md">
            Получи Client-Id и Api-Key в личном кабинете Ozon Seller (Настройки → Сертификаты API).
            Для рекламы нужны отдельные ключи из Ozon Performance.
          </p>
          <Link to="/cabinets/new" className="mt-6">
            <Button>
              <Plus className="w-4 h-4" />
              Добавить первый кабинет
            </Button>
          </Link>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {cabinets.map((cab) => {
            const tier = TIER_BY_VALUE[cab.premium_tier] || TIER_BY_VALUE.free
            const statusMeta = STATUS_LABEL[cab.status] || { label: cab.status, tone: 'muted' as const }
            return (
              <Link
                to={`/cabinets/${cab.id}`}
                key={cab.id}
                className="group focus:outline-none"
              >
                <Card className="p-6 hover:border-fg-subtle hover:shadow-elev transition-all h-full">
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="min-w-0">
                      <h3 className="text-base font-semibold text-fg truncate group-hover:underline underline-offset-4">
                        {cab.name}
                      </h3>
                      <p className="text-xs text-fg-muted mt-0.5">
                        {tier.emoji} {tier.label}
                      </p>
                    </div>
                    <ArrowUpRight className="w-4 h-4 text-fg-subtle group-hover:text-fg transition-colors shrink-0" />
                  </div>

                  <div className="flex items-center gap-2 text-xs mb-3 flex-wrap">
                    <span
                      className={cn(
                        'inline-flex items-center gap-1.5',
                        statusMeta.tone === 'success' && 'text-success',
                        statusMeta.tone === 'error' && 'text-error',
                        statusMeta.tone === 'muted' && 'text-fg-subtle',
                      )}
                    >
                      <span
                        className={cn(
                          'w-1.5 h-1.5 rounded-full',
                          statusMeta.tone === 'success' && 'bg-success',
                          statusMeta.tone === 'error' && 'bg-error',
                          statusMeta.tone === 'muted' && 'bg-fg-subtle',
                        )}
                      />
                      {statusMeta.label}
                    </span>
                    {cab.has_performance_api && (
                      <span
                        className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-fg-muted bg-bg-subtle rounded-full px-2 py-0.5"
                        title="Performance API подключён — синхронизация рекламных кампаний и ДРР/ROAS"
                      >
                        <Megaphone className="w-2.5 h-2.5" />
                        Реклама
                      </span>
                    )}
                  </div>

                  <div className="pt-3 border-t border-border-subtle text-xs text-fg-muted">
                    Последняя синхр.:{' '}
                    {cab.last_sync_at ? formatRelativeTime(cab.last_sync_at) : 'не было'}
                  </div>

                  {cab.last_sync_error && (
                    <div className="mt-2 inline-flex items-start gap-1.5 text-[11px] text-error">
                      <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
                      <span className="line-clamp-2">{getErrorMessage(cab.last_sync_error)}</span>
                    </div>
                  )}
                </Card>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
