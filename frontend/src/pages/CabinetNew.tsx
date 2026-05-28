import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, ExternalLink, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'
import {
  PREMIUM_TIER_OPTIONS,
  PremiumTierSelect,
  type PremiumTier,
} from '@/components/PremiumTierSelect'

type PerfTestState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; expiresIn: number | null }
  | { kind: 'error'; message: string }

export function CabinetNew() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [clientId, setClientId] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [premiumTier, setPremiumTier] = useState<PremiumTier>('free')
  const [perfClientId, setPerfClientId] = useState('')
  const [perfClientSecret, setPerfClientSecret] = useState('')
  const [perfTest, setPerfTest] = useState<PerfTestState>({ kind: 'idle' })

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await api.post('/ozon-accounts/', {
        name,
        client_id: clientId,
        api_key: apiKey,
        premium_tier: premiumTier,
        perf_client_id: perfClientId || null,
        perf_client_secret: perfClientSecret || null,
      })
      navigate('/cabinets')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
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

  return (
    <div className="max-w-3xl mx-auto">
      <Link
        to="/cabinets"
        className="inline-flex items-center gap-1 text-sm text-fg-muted hover:text-fg mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Назад к списку
      </Link>

      <div className="mb-8">
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Подключить кабинет Ozon</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          Введи API-ключи и выбери тариф. Performance API — опционально, для рекламы.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-8">
        <div className="space-y-6">
          {/* ============ Базовые ============ */}
          <Card className="p-6 space-y-4">
            <h2 className="text-sm font-semibold text-fg uppercase tracking-wider">Основное</h2>
            <Input
              label="Название кабинета"
              placeholder="STOLZ KRAFT — основной"
              value={name}
              onChange={(e) => setName(e.target.value)}
              hint="Произвольное имя для удобства"
              required
              autoFocus
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
              placeholder="12345-abcde"
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
              placeholder="••••••••••••••••••••••••"
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

          <div className="flex items-center gap-3">
            <Button type="submit" loading={loading}>
              Подключить кабинет
            </Button>
            <Link to="/cabinets">
              <Button type="button" variant="secondary">
                Отмена
              </Button>
            </Link>
          </div>
        </div>

        {/* ============ Sidebar info ============ */}
        <aside className="space-y-4">
          <Card className="p-5 bg-bg-subtle border-border-subtle">
            <h3 className="text-sm font-semibold text-fg mb-2">Что даст подключение</h3>
            <ul className="text-xs text-fg-muted space-y-1.5 list-disc list-inside">
              <li>Каждый час синхронизация товаров</li>
              <li>Снапшоты остатков и цен</li>
              <li>Заказы, транзакции, аналитика</li>
              <li>Если есть PA — ДРР и ROAS в P&L</li>
            </ul>
          </Card>

          <Card className="p-5">
            <h3 className="text-sm font-semibold text-fg mb-3">Тарифы Ozon — что открывают</h3>
            <ul className="text-xs space-y-2.5">
              {PREMIUM_TIER_OPTIONS.map((opt) => (
                <li key={opt.value} className="leading-relaxed">
                  <div className="font-medium text-fg">
                    {opt.emoji} {opt.label}
                  </div>
                  <div className="text-fg-muted">{opt.summary}</div>
                </li>
              ))}
            </ul>
          </Card>
        </aside>
      </form>
    </div>
  )
}
