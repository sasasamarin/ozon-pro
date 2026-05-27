import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Store,
  TrendingUp,
  Package,
  ArrowUpRight,
  Plus,
  Sparkles,
  ArrowDownRight,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Sparkline } from '@/components/ui/Sparkline'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, formatRelativeTime, cn } from '@/lib/utils'
import { getCurrentUser } from '@/lib/auth'

interface DashboardData {
  cabinets_count: number
  total_revenue: number
  total_stock: number
  recent_activity: Array<{ id: string; cabinet_name: string; event: string; created_at: string }>
}

// Placeholder series until backend exposes time-series.
const TREND_UP = [34, 38, 36, 42, 45, 41, 50, 54, 51, 58, 62, 60, 68, 72, 75]
const TREND_FLAT = [42, 44, 41, 43, 45, 44, 46, 45, 47, 46, 48, 47, 49, 48, 50]
const TREND_REVENUE = [48, 52, 50, 58, 62, 60, 68, 65, 72, 78, 76, 84, 88, 92, 96]

export function Dashboard() {
  const user = getCurrentUser()
  const { data, isLoading } = useQuery<DashboardData>({
    queryKey: ['dashboard'],
    queryFn: async () => {
      const res = await api.get('/dashboard/')
      return res.data
    },
  })

  const stats = [
    {
      label: 'Кабинеты',
      value: data?.cabinets_count ?? 0,
      icon: Store,
      iconBg: 'from-indigo-50 to-white',
      iconColor: 'text-indigo-500',
      trend: TREND_FLAT,
      trendColor: 'text-fg-muted',
      delta: null as { value: string; direction: 'up' | 'down' } | null,
      formatter: (v: number) => formatNumber(v),
    },
    {
      label: 'Оборот за 30 дней',
      value: data?.total_revenue ?? 0,
      icon: TrendingUp,
      iconBg: 'from-rose-50 to-white',
      iconColor: 'text-rose-500',
      trend: TREND_REVENUE,
      trendColor: 'text-success',
      delta: { value: '+18.4%', direction: 'up' as const },
      formatter: (v: number) => formatCurrency(v),
    },
    {
      label: 'Остатки (шт)',
      value: data?.total_stock ?? 0,
      icon: Package,
      iconBg: 'from-amber-50 to-white',
      iconColor: 'text-amber-600',
      trend: TREND_UP,
      trendColor: 'text-success',
      delta: { value: '+4.2%', direction: 'up' as const },
      formatter: (v: number) => formatNumber(v),
    },
  ]

  const hasCabinets = (data?.cabinets_count ?? 0) > 0
  const companyName = user?.full_name?.split(' ')[0] || user?.email?.split('@')[0] || 'там'

  return (
    <div className="relative">
      {/* Ambient background */}
      <div
        aria-hidden
        className="absolute -top-20 -right-20 w-[520px] h-[520px] rounded-full bg-aurora-soft blur-3xl pointer-events-none -z-0"
      />

      <div className="relative flex flex-col gap-8">
        {/* Header */}
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-border-subtle bg-bg-subtle/60 backdrop-blur-sm px-2.5 py-1 text-xs font-medium text-fg-muted">
              <Sparkles className="w-3 h-3" />
              Сводка · 30 дней
            </div>
            <h1 className="text-3xl font-semibold text-fg tracking-tight mt-3">
              Привет, {companyName}
            </h1>
            <p className="text-sm text-fg-muted mt-1.5">
              Управление кабинетами Ozon и аналитика продаж
            </p>
          </div>
          {hasCabinets && (
            <Link to="/cabinets/new">
              <Button variant="secondary">
                <Plus className="w-4 h-4" />
                Кабинет
              </Button>
            </Link>
          )}
        </div>

        {/* Stat cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {stats.map(({ label, value, icon: Icon, iconBg, iconColor, trend, trendColor, delta, formatter }) => (
            <Card
              key={label}
              className="p-5 relative overflow-hidden hover:shadow-elev hover:border-border transition-all duration-200"
            >
              <div className="flex items-center justify-between mb-4">
                <div
                  className={cn(
                    'w-9 h-9 rounded-lg bg-gradient-to-br border border-white shadow-sm flex items-center justify-center',
                    iconBg
                  )}
                >
                  <Icon className={cn('w-4 h-4', iconColor)} />
                </div>
                {delta && (
                  <span
                    className={cn(
                      'inline-flex items-center gap-0.5 text-[11px] font-semibold px-2 py-0.5 rounded-full tabular-nums',
                      delta.direction === 'up'
                        ? 'text-success bg-green-50'
                        : 'text-error bg-red-50'
                    )}
                  >
                    {delta.direction === 'up' ? (
                      <ArrowUpRight className="w-3 h-3" />
                    ) : (
                      <ArrowDownRight className="w-3 h-3" />
                    )}
                    {delta.value}
                  </span>
                )}
              </div>
              <p className="text-xs font-medium text-fg-muted uppercase tracking-wider">{label}</p>
              <p className="text-[28px] leading-tight font-semibold text-fg mt-1 tabular-nums">
                {isLoading ? (
                  <span className="inline-block w-24 h-7 bg-bg-subtle rounded animate-pulse" />
                ) : (
                  formatter(value)
                )}
              </p>
              <div className={cn('mt-3 -mx-1', trendColor)}>
                <Sparkline points={trend} />
              </div>
            </Card>
          ))}
        </div>

        {/* Empty state OR recent activity */}
        {!hasCabinets ? (
          <Card className="relative overflow-hidden p-12 flex flex-col items-center text-center">
            <div
              aria-hidden
              className="absolute inset-0 bg-aurora opacity-40 pointer-events-none"
            />
            <div className="absolute inset-0 bg-grid-faint opacity-40 pointer-events-none" />
            <div className="relative w-14 h-14 rounded-2xl bg-white border border-border-subtle shadow-glass flex items-center justify-center mb-5">
              <Store className="w-6 h-6 text-fg-muted" />
            </div>
            <h3 className="relative text-lg font-semibold text-fg">Пока нет кабинетов</h3>
            <p className="relative text-sm text-fg-muted mt-1.5 max-w-md">
              Подключи свой первый кабинет Ozon, чтобы получить аналитику по продажам, остаткам и финансам.
            </p>
            <Link to="/cabinets/new" className="relative mt-6">
              <Button>
                <Plus className="w-4 h-4" />
                Добавить кабинет Ozon
              </Button>
            </Link>
          </Card>
        ) : (
          <Card className="overflow-hidden">
            <div className="px-6 py-4 border-b border-border-subtle flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-fg">Последние действия</h2>
                <p className="text-xs text-fg-muted mt-0.5">События по всем кабинетам</p>
              </div>
              <Link
                to="/cabinets"
                className="text-sm text-fg-muted hover:text-fg flex items-center gap-1 transition-colors"
              >
                Все кабинеты <ArrowUpRight className="w-3.5 h-3.5" />
              </Link>
            </div>
            <ul className="divide-y divide-border-subtle">
              {(data?.recent_activity || []).map((item) => (
                <li
                  key={item.id}
                  className="px-6 py-3.5 flex items-center justify-between hover:bg-bg-subtle/50 transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="w-1.5 h-1.5 rounded-full bg-success shrink-0" />
                    <span className="text-sm font-medium text-fg truncate">{item.cabinet_name}</span>
                    <span className="text-sm text-fg-muted truncate">{item.event}</span>
                  </div>
                  <span className="text-xs text-fg-subtle font-mono shrink-0 ml-3">
                    {formatRelativeTime(item.created_at)}
                  </span>
                </li>
              ))}
              {(data?.recent_activity || []).length === 0 && (
                <li className="px-6 py-8 text-center text-sm text-fg-muted">
                  Активности ещё нет
                </li>
              )}
            </ul>
          </Card>
        )}
      </div>
    </div>
  )
}
