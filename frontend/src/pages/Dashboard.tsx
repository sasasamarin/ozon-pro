import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Store, TrendingUp, Package, ArrowUpRight, Plus } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, formatRelativeTime } from '@/lib/utils'
import { getCurrentUser } from '@/lib/auth'

interface DashboardData {
  cabinets_count: number
  total_revenue: number
  total_stock: number
  recent_activity: Array<{ id: string; cabinet_name: string; event: string; created_at: string }>
}

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
      formatter: (v: number) => formatNumber(v),
    },
    {
      label: 'Оборот за 30 дней',
      value: data?.total_revenue ?? 0,
      icon: TrendingUp,
      formatter: (v: number) => formatCurrency(v),
    },
    {
      label: 'Остатки (шт)',
      value: data?.total_stock ?? 0,
      icon: Package,
      formatter: (v: number) => formatNumber(v),
    },
  ]

  const hasCabinets = (data?.cabinets_count ?? 0) > 0

  return (
    <div className="flex flex-col gap-8">
      {/* Header */}
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">
            Привет, {user?.full_name || user?.email?.split('@')[0]}
          </h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Управление кабинетами Ozon и аналитика продаж
          </p>
        </div>
        {!hasCabinets && (
          <Link to="/cabinets/new">
            <Button>
              <Plus className="w-4 h-4" />
              Добавить кабинет
            </Button>
          </Link>
        )}
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {stats.map(({ label, value, icon: Icon, formatter }) => (
          <Card key={label} className="p-6 hover:border-fg-subtle transition-colors">
            <div className="flex items-start justify-between mb-3">
              <div className="w-9 h-9 rounded-md bg-bg-subtle flex items-center justify-center">
                <Icon className="w-4 h-4 text-fg-muted" />
              </div>
            </div>
            <p className="text-xs font-medium text-fg-muted uppercase tracking-wider">{label}</p>
            <p className="text-2xl font-semibold text-fg mt-1.5 tabular-nums">
              {isLoading ? <span className="inline-block w-20 h-7 bg-bg-subtle rounded animate-pulse" /> : formatter(value)}
            </p>
          </Card>
        ))}
      </div>

      {/* Empty state OR recent activity */}
      {!hasCabinets ? (
        <Card className="p-12 flex flex-col items-center text-center">
          <div className="w-14 h-14 rounded-full bg-bg-subtle flex items-center justify-center mb-4">
            <Store className="w-6 h-6 text-fg-muted" />
          </div>
          <h3 className="text-lg font-semibold text-fg">Пока нет кабинетов</h3>
          <p className="text-sm text-fg-muted mt-1.5 max-w-md">
            Подключи свой первый кабинет Ozon, чтобы получить аналитику по продажам, остаткам и финансам.
          </p>
          <Link to="/cabinets/new" className="mt-6">
            <Button>
              <Plus className="w-4 h-4" />
              Добавить кабинет Ozon
            </Button>
          </Link>
        </Card>
      ) : (
        <Card>
          <div className="px-6 py-4 border-b border-border-subtle flex items-center justify-between">
            <h2 className="text-base font-semibold text-fg">Последние действия</h2>
            <Link to="/cabinets" className="text-sm text-fg-muted hover:text-fg flex items-center gap-1">
              Все кабинеты <ArrowUpRight className="w-3.5 h-3.5" />
            </Link>
          </div>
          <ul className="divide-y divide-border-subtle">
            {(data?.recent_activity || []).map((item) => (
              <li key={item.id} className="px-6 py-3 flex items-center justify-between hover:bg-bg-subtle/50 transition-colors">
                <div className="flex items-center gap-3">
                  <div className="w-1.5 h-1.5 rounded-full bg-success" />
                  <span className="text-sm font-medium text-fg">{item.cabinet_name}</span>
                  <span className="text-sm text-fg-muted">{item.event}</span>
                </div>
                <span className="text-xs text-fg-subtle font-mono">{formatRelativeTime(item.created_at)}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
