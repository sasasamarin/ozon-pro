import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Target, Sparkles } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'

interface FunnelKPI {
  impressions: number
  to_cart: number
  orders: number
  delivered: number
  cart_conv_pct: number | null
  order_conv_pct: number | null
  delivery_conv_pct: number | null
  overall_conv_pct: number | null
}

/**
 * Обратная воронка: ввод цели → расчёт нужных показов/корзин.
 * Использует текущие конверсии воронки → масштабирует к нужной цели.
 */
export function ReverseFunnel() {
  const [targetRevenue, setTargetRevenue] = useState('5000000')
  const [aov, setAov] = useState('5000')

  const { data: funnel } = useQuery<{ kpi: FunnelKPI }>({
    queryKey: ['funnel-current'],
    queryFn: async () => (await api.get('/analytics/funnel/?days=30&compare=false')).data,
  })

  const calc = useMemo(() => {
    const target = parseFloat(targetRevenue) || 0
    const avgPrice = parseFloat(aov) || 1
    const neededDelivered = target / avgPrice

    if (!funnel?.kpi) return null
    const k = funnel.kpi
    if (!k.delivery_conv_pct || !k.order_conv_pct || !k.cart_conv_pct) return null

    const neededOrders = neededDelivered / (k.delivery_conv_pct / 100)
    const neededCart = neededOrders / (k.order_conv_pct / 100)
    const neededImpressions = neededCart / (k.cart_conv_pct / 100)

    const currentRevenue = k.delivered * avgPrice
    const ratio = target / Math.max(currentRevenue, 1)

    return {
      neededImpressions,
      neededCart,
      neededOrders,
      neededDelivered,
      currentRevenue,
      ratio,
    }
  }, [targetRevenue, aov, funnel])

  return (
    <div className="flex flex-col gap-6">
      <div>
        <div className="inline-flex items-center gap-2 rounded-full border border-border-subtle bg-bg-subtle/60 px-2.5 py-1 text-xs font-medium text-fg-muted">
          <Sparkles className="w-3 h-3" />
          Killer-feature
        </div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight mt-3">Обратная воронка</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          Задай цель → AI рассчитает сколько показов / переходов в корзину нужно для её достижения.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="p-5 lg:col-span-1">
          <h3 className="text-base font-semibold text-fg mb-4 flex items-center gap-2">
            <Target className="w-4 h-4 text-fg-muted" />
            Цель
          </h3>
          <div className="flex flex-col gap-3">
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">
                Целевая выручка ₽
              </label>
              <Input value={targetRevenue} onChange={(e) => setTargetRevenue(e.target.value)} type="number" />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">
                Средний чек ₽
              </label>
              <Input value={aov} onChange={(e) => setAov(e.target.value)} type="number" />
            </div>
          </div>
          {funnel?.kpi && (
            <div className="mt-5 pt-4 border-t border-border-subtle text-xs text-fg-muted space-y-1">
              <div className="font-medium text-fg mb-2">Текущие конверсии (30 дн):</div>
              <div>В корзину: <strong className="text-fg">{funnel.kpi.cart_conv_pct?.toFixed(2)}%</strong></div>
              <div>Корзина→заказ: <strong className="text-fg">{funnel.kpi.order_conv_pct?.toFixed(2)}%</strong></div>
              <div>Заказ→доставка: <strong className="text-fg">{funnel.kpi.delivery_conv_pct?.toFixed(2)}%</strong></div>
              <div>Сквозная: <strong className="text-fg">{funnel.kpi.overall_conv_pct?.toFixed(2)}%</strong></div>
            </div>
          )}
        </Card>

        <Card className="p-5 lg:col-span-2">
          <h3 className="text-base font-semibold text-fg mb-4">Что нужно</h3>
          {!calc ? (
            <p className="text-sm text-fg-muted">Введите цель — AI рассчитает воронку.</p>
          ) : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
                <Tile label="Показы" value={formatNumber(calc.neededImpressions)} />
                <Tile label="В корзину" value={formatNumber(calc.neededCart)} />
                <Tile label="Заказы" value={formatNumber(calc.neededOrders)} />
                <Tile label="Доставлено" value={formatNumber(calc.neededDelivered)} accent />
              </div>

              <div className="text-sm text-fg-muted space-y-1.5">
                <div>Текущая выручка 30д: <strong className="text-fg">{formatCurrency(calc.currentRevenue)}</strong></div>
                <div>Цель: <strong className="text-fg">{formatCurrency(parseFloat(targetRevenue))}</strong></div>
                <div>Нужно вырасти в: <strong className={cn(
                  calc.ratio > 1 ? 'text-rose-700' : 'text-emerald-700',
                )}>{calc.ratio.toFixed(2)}×</strong></div>
              </div>

              <div className="mt-5 p-3 rounded-md bg-indigo-50 border border-indigo-200 text-sm text-indigo-900">
                <strong>Сценарии для достижения:</strong>
                <ul className="list-disc list-inside mt-2 space-y-0.5">
                  <li>Увеличить рекламу для роста показов в {calc.ratio.toFixed(1)}× раз</li>
                  <li>Улучшить карточки → +20% конверсии в корзину</li>
                  <li>Снизить цену на 5% → +15% конверсии в заказ</li>
                  <li>Добавить отзывы → +10% к выкупу</li>
                </ul>
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  )
}

function Tile({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={cn(
      'rounded-md border px-3 py-3',
      accent ? 'border-indigo-300 bg-indigo-50' : 'border-border-subtle bg-bg-subtle/30',
    )}>
      <div className="text-[10px] font-medium text-fg-muted uppercase tracking-wider">{label}</div>
      <div className={cn('text-lg font-semibold mt-1 tabular-nums', accent ? 'text-indigo-700' : 'text-fg')}>
        {value}
      </div>
    </div>
  )
}
