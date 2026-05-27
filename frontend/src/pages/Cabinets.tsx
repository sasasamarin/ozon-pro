import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Plus, Store, RefreshCw } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { api } from '@/lib/api'
import { formatRelativeTime } from '@/lib/utils'

interface Cabinet {
  id: string
  name: string
  ozon_client_id: string
  is_active: boolean
  last_sync_at?: string
  created_at: string
}

export function Cabinets() {
  const { data, isLoading } = useQuery<Cabinet[]>({
    queryKey: ['cabinets'],
    queryFn: async () => {
      const res = await api.get('/ozon-accounts/')
      return res.data
    },
  })

  const cabinets = data || []

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Кабинеты Ozon</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            {cabinets.length > 0 ? `Подключено кабинетов: ${cabinets.length}` : 'Подключи свой первый кабинет'}
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
          {cabinets.map((cab) => (
            <Card key={cab.id} className="p-6 hover:border-fg-subtle transition-all hover:shadow-sm">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="text-base font-semibold text-fg">{cab.name}</h3>
                  <p className="text-xs text-fg-muted font-mono mt-0.5">Client ID: {cab.ozon_client_id}</p>
                </div>
                <div className={`flex items-center gap-1.5 text-xs ${cab.is_active ? 'text-success' : 'text-fg-subtle'}`}>
                  <div className={`w-1.5 h-1.5 rounded-full ${cab.is_active ? 'bg-success' : 'bg-fg-subtle'}`} />
                  {cab.is_active ? 'Активен' : 'Отключён'}
                </div>
              </div>
              <div className="flex items-center justify-between pt-3 border-t border-border-subtle">
                <span className="text-xs text-fg-muted">
                  Последняя синхр.: {cab.last_sync_at ? formatRelativeTime(cab.last_sync_at) : 'не было'}
                </span>
                <button className="text-xs text-fg-muted hover:text-fg flex items-center gap-1 transition-colors">
                  <RefreshCw className="w-3 h-3" />
                  Синхронизировать
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
