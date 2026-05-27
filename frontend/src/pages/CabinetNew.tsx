import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'

export function CabinetNew() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [clientId, setClientId] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await api.post('/ozon-accounts/', {
        name,
        ozon_client_id: clientId,
        ozon_api_key: apiKey,
      })
      navigate('/cabinets')
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Не удалось добавить кабинет')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <Link to="/cabinets" className="inline-flex items-center gap-1 text-sm text-fg-muted hover:text-fg mb-6 transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Назад к списку
      </Link>

      <div className="mb-8">
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Подключить кабинет Ozon</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          Введи Client-Id и Api-Key из личного кабинета Ozon Seller
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-8">
        <Card className="p-6">
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <Input
              label="Название кабинета"
              placeholder="STOLZ KRAFT — основной"
              value={name}
              onChange={(e) => setName(e.target.value)}
              hint="Произвольное имя для удобства"
              required
              autoFocus
            />
            <Input
              label="Client ID"
              placeholder="12345"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              className="font-mono"
              required
            />
            <Input
              label="Api Key"
              type="password"
              placeholder="••••••••-••••-••••-••••-••••••••••••"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className="font-mono"
              hint="Будет зашифрован при сохранении"
              required
            />
            {error && (
              <div className="text-sm text-error bg-red-50 border border-red-200 rounded-md px-3 py-2">
                {error}
              </div>
            )}
            <div className="flex items-center gap-3 mt-2">
              <Button type="submit" loading={loading}>
                Подключить кабинет
              </Button>
              <Link to="/cabinets">
                <Button type="button" variant="secondary">
                  Отмена
                </Button>
              </Link>
            </div>
          </form>
        </Card>

        <aside className="space-y-4">
          <Card className="p-5 bg-bg-subtle border-border-subtle">
            <h3 className="text-sm font-semibold text-fg mb-2">Где взять ключи?</h3>
            <ol className="text-xs text-fg-muted space-y-1.5 list-decimal list-inside">
              <li>Зайди в Ozon Seller</li>
              <li>Настройки → Сертификаты API</li>
              <li>Создай новый ключ с правами <span className="font-mono text-fg">Admin</span></li>
              <li>Скопируй Client-Id и Api-Key</li>
            </ol>
            <a
              href="https://seller.ozon.ru/app/settings/api-keys"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-accent font-medium mt-3 hover:underline"
            >
              Открыть Ozon Seller
              <ExternalLink className="w-3 h-3" />
            </a>
          </Card>
        </aside>
      </div>
    </div>
  )
}
