import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowRight } from 'lucide-react'

interface CostWarningBannerProps {
  /** Сколько товаров с confidence=missing или NULL cost_price. */
  count: number
  /** Контекст где показывается — влияет на текст. */
  context?: 'profit' | 'romi' | 'general'
  className?: string
}

/**
 * Жёлтая плашка «себестоимость не введена — прибыль приблизительная».
 *
 * Показываем на /dashboard, /finance/pnl, /products/{id}, /procurement/forecast
 * и любых страницах где видны прибыль/ROMI/ROI. Скрывается автоматически когда
 * count=0.
 *
 * UI-инвариант: одна и та же копия везде, чтобы не путать юзера.
 */
export function CostWarningBanner({ count, context = 'general', className }: CostWarningBannerProps) {
  if (count <= 0) return null

  const detail =
    context === 'profit'
      ? 'COGS = 0 для этих товаров → их вклад в чистую прибыль завышен на полную себестоимость. Введи реальные цифры — иначе цифры P&L ВРУТ.'
      : context === 'romi'
      ? 'ROMI/ROI без себестоимости — бессмысленны. Цифры выглядят слишком радужно, не принимай решения по ним.'
      : 'Себестоимость = 0 для части товаров → вся аналитика прибыли по ним искажена. Заполни до использования.'

  return (
    <div
      className={
        'flex items-start gap-3 rounded-lg border border-rose-300 bg-rose-50 px-4 py-3 ' +
        (className ?? '')
      }
    >
      <AlertTriangle className="w-5 h-5 text-rose-700 mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-rose-900">
          ⚠ Прибыль ЗАВЫШЕНА: себестоимость не введена ({count} {pluralize(count)})
        </p>
        <p className="text-sm text-rose-800/90 mt-0.5">{detail}</p>
      </div>
      <Link
        to="/products?missing_cost=1&arch=all"
        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md bg-rose-900 hover:bg-rose-800 text-white text-xs font-medium shrink-0 transition-colors"
      >
        Заполнить сейчас
        <ArrowRight className="w-3.5 h-3.5" />
      </Link>
    </div>
  )
}

function pluralize(n: number): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod100 >= 11 && mod100 <= 14) return 'товаров'
  if (mod10 === 1) return 'товар'
  if (mod10 >= 2 && mod10 <= 4) return 'товара'
  return 'товаров'
}
