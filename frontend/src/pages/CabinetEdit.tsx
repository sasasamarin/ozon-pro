import { useState, useEffect } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  ExternalLink,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Trash2,
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'
import { formatRelativeTime } from '@/lib/utils'
import {
  PremiumTierSelect,
  type PremiumTier,
} from '@/components/PremiumTierSelect'

interface CabinetFull {
  id: string
  name: string
  description: string | null
  status: string
  is_active: boolean
  premium_tier: PremiumTier
  last_sync_at: string | null
  last_sync_error: string | null
  has_performance_api: boolean
}

type PerfTestState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; expiresIn: number | null }
  | { kind: 'error'; message: string }

export function CabinetEdit() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { data, isLoading, error: loadError } = useQuery<CabinetFull>({
    queryKey: ['ozon-account', id],
    queryFn: async () => {
      const res = await api.get(`/ozon-accounts/${id}`)
      return res.data
    },
    enabled: !!id,
  })

  const [name, setName] = useState('')
  const [premiumTier, setPremiumTier] = useState<PremiumTier>('free')
  const [clientId, setClientId] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [perfClientId, setPerfClientId] = useState('')
  const [perfClientSecret, setPerfClientSecret] = useState('')
  const [perfTest, setPerfTest] = useState<PerfTestState>({ kind: 'idle' })

  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (data) {
      setName(data.name)
      setPremiumTier(data.premium_tier)
    }
  }, [data])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!id) return
    setError('')
    setSaving(true)
    try {
      const payload: Record<string, unknown> = {
        name,
        premium_tier: premiumTier,
      }
      // Только заполненные секреты идут в PATCH.
      if (clientId.trim()) payload.client_id = clientId.trim()
      if (apiKey.trim()) payload.api_key = apiKey.trim()
      if (perfClientId.trim()) payload.perf_client_id = perfClientId.trim()
      if (perfClientSecret.trim()) payload.perf_client_secret = perfClientSecret.trim()

      await api.patch(`/ozon-accounts/${id}`, payload)
      navigate('/cabinets')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  async function handlePerfTest() {
    if (!perfClientId || !perfClientSecret) return
    setPerfTest({ kind: 'loading' })
    try {
      const res = await api.post('/ozon-accounts/test-perf-credentials', {
        perf_client_id: perfClientId,
        perf_client_secret: perfClientSecret,
      })
      if (res.data.ok) {
        setPerfTest({ kind: 'ok', expiresIn: res.data.expires_in ?? null })
      } else {
        setPerfTest({ kind: 'error', message: res.data.error || 'Не удалось получить токен' })
      }
    } catch (err) {
      setPerfTest({ kind: 'error', message: getErrorMessage(err) })
    }
  }

  async function handleDelete() {
    if (!id) return
    if (!confirm('Удалить кабинет? Данные останутся, но синхронизации остановятся.')) return
    setDeleting(true)
    try {
      await api.delete(`/ozon-accounts/${id}`)
      navigate('/cabinets')
    } catch (err) {
      setError(getErrorMessage(err))
      setDeleting(false)
    }
  }

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto py-20 flex items-center justify-center text-fg-muted">
        <Loader2 className="w-5 h-5 animate-spin mr-2" />
        Загрузка кабинета…
      </div>
    )
  }

  if (loadError || !data) {
    return (
      <div className="max-w-3xl mx-auto py-20">
        <Card className="p-8 text-center">
          <AlertCircle className="w-8 h-8 text-error mx-auto mb-3" />
          <h2 className="text-lg font-semibold text-fg">Кабинет не найден</h2>
          <p className="text-sm text-fg-muted mt-1">{getErrorMessage(loadError)}</p>
          <Link to="/cabinets" className="inline-block mt-4">
            <Button variant="secondary">К списку</Button>
          </Link>
        </Card>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto">
      <Link
        to="/cabinets"
        className="inline-flex items-center gap-1 text-sm text-fg-muted hover:text-fg mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Назад к списку
      </Link>

      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">{data.name}</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Статус: <span className="font-medium text-fg">{data.status}</span>
            {data.last_sync_at && (
              <>
                {' · '}последняя синхр.{' '}
                <span className="font-mono">{formatRelativeTime(data.last_sync_at)}</span>
              </>
            )}
            {data.has_performance_api && (
              <span className="ml-2 inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-fg-muted bg-bg-subtle rounded-full px-2 py-0.5">
                PA подключён
              </span>
            )}
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* ============ Основное ============ */}
        <Card className="p-6 space-y-4">
          <h2 className="text-sm font-semibold text-fg uppercase tracking-wider">Основное</h2>
          <Input
            label="Название кабинета"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <PremiumTierSelect value={premiumTier} onChange={setPremiumTier} />
        </Card>

        {/* ============ Seller API ============ */}
        <Card className="p-6 space-y-4">
          <div>
            <h2 className="text-sm font-semibold text-fg uppercase tracking-wider">Seller API</h2>
            <p className="text-xs text-fg-muted mt-1">
              Где взять — Ozon Seller:{' '}
              <a
                href="https://seller.ozon.ru/app/settings/api-keys"
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent hover:underline"
              >
                Настройки → Сертификаты API <ExternalLink className="inline w-3 h-3" />
              </a>
            </p>
          </div>
          <Input
            label="Client ID"
            placeholder="Оставь пустым чтобы не менять"
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            className="font-mono"
          />
          <Input
            label="Api Key"
            type="password"
            placeholder="Оставь пустым чтобы не менять"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            className="font-mono"
          />
        </Card>

        {/* ============ Performance API ============ */}
        <Card className="p-6 space-y-4">
          <div>
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-fg uppercase tracking-wider">
                Performance API <span className="text-fg-subtle font-normal normal-case ml-1">(для рекламы)</span>
              </h2>
              <span className="text-[10px] font-semibold text-fg-subtle uppercase tracking-wider">
                Опционально
              </span>
            </div>
            <p className="text-xs text-fg-muted mt-1">
              Где взять — Ozon Performance:{' '}
              <a
                href="https://performance.ozon.ru/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent hover:underline"
              >
                Настройки → API ключи <ExternalLink className="inline w-3 h-3" />
              </a>
            </p>
          </div>
          <Input
            label="Client ID"
            placeholder={data.has_performance_api ? 'Зашифрован · оставь пустым чтобы не менять' : '12345-abcde'}
            value={perfClientId}
            onChange={(e) => {
              setPerfClientId(e.target.value)
              setPerfTest({ kind: 'idle' })
            }}
            className="font-mono"
          />
          <Input
            label="Client Secret"
            type="password"
            placeholder={data.has_performance_api ? 'Зашифрован · оставь пустым чтобы не менять' : '••••••••••••••••••••••••'}
            value={perfClientSecret}
            onChange={(e) => {
              setPerfClientSecret(e.target.value)
              setPerfTest({ kind: 'idle' })
            }}
            className="font-mono"
          />

          <div className="flex items-center gap-3">
            <Button
              type="button"
              variant="secondary"
              onClick={handlePerfTest}
              disabled={!perfClientId || !perfClientSecret || perfTest.kind === 'loading'}
              size="sm"
            >
              {perfTest.kind === 'loading' && (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              )}
              Тест подключения
            </Button>
            {perfTest.kind === 'ok' && (
              <span className="inline-flex items-center gap-1.5 text-xs text-success">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Токен получен
                {perfTest.expiresIn && (
                  <span className="text-fg-subtle">· живёт {Math.round(perfTest.expiresIn / 60)} мин</span>
                )}
              </span>
            )}
            {perfTest.kind === 'error' && (
              <span className="inline-flex items-start gap-1.5 text-xs text-error">
                <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span className="break-all">{perfTest.message}</span>
              </span>
            )}
          </div>
        </Card>

        {error && (
          <div className="text-sm text-error bg-red-50 border border-red-200 rounded-md px-3 py-2">
            {error}
          </div>
        )}

        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Button type="submit" loading={saving}>
              Сохранить
            </Button>
            <Link to="/cabinets">
              <Button type="button" variant="secondary">
                Отмена
              </Button>
            </Link>
          </div>
          <Button
            type="button"
            variant="danger"
            size="sm"
            onClick={handleDelete}
            loading={deleting}
          >
            <Trash2 className="w-3.5 h-3.5" />
            Удалить кабинет
          </Button>
        </div>
      </form>
    </div>
  )
}
