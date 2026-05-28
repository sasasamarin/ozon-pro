import { cn } from '@/lib/utils'

export type PremiumTier = 'free' | 'premium' | 'premium_plus' | 'premium_pro'

export interface PremiumTierOption {
  value: PremiumTier
  label: string
  emoji: string
  price: string
  summary: string
}

export const PREMIUM_TIER_OPTIONS: PremiumTierOption[] = [
  {
    value: 'free',
    label: 'Бесплатный',
    emoji: '🆓',
    price: '0₽',
    summary: 'Базовый Seller API — товары, заказы, цены, аналитика.',
  },
  {
    value: 'premium',
    label: 'Premium',
    emoji: '💎',
    price: '5 990₽/мес',
    summary: 'То же что Free + скидка покупателям. По API — эквивалент Free.',
  },
  {
    value: 'premium_plus',
    label: 'Premium Plus',
    emoji: '⭐',
    price: '24 990₽/мес',
    summary: 'Конкуренты (до 8), отчёт о реализации, расширенная аналитика.',
  },
  {
    value: 'premium_pro',
    label: 'Premium Pro',
    emoji: '🚀',
    price: '24 990₽ + 2.5%',
    summary:
      'Всё из Plus + отзывы, вопросы, поисковая аналитика, конкуренты без лимита, кросс-площадки.',
  },
]

interface Props {
  value: PremiumTier
  onChange: (v: PremiumTier) => void
  disabled?: boolean
}

export function PremiumTierSelect({ value, onChange, disabled }: Props) {
  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm font-medium text-fg">Тариф на Ozon</label>
      <p className="text-xs text-fg-muted -mt-1">
        Влияет на то, какие данные мы тянем (конкуренты, отзывы, реализация — только на Plus/Pro).
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {PREMIUM_TIER_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            disabled={disabled}
            onClick={() => onChange(opt.value)}
            className={cn(
              'text-left flex items-start gap-3 p-3 rounded-lg border transition-all',
              value === opt.value
                ? 'border-fg bg-bg-subtle/60 shadow-sm'
                : 'border-border hover:border-fg-subtle hover:bg-bg-subtle/40',
              disabled && 'opacity-50 cursor-not-allowed'
            )}
          >
            <div className="text-xl leading-none shrink-0">{opt.emoji}</div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-fg">{opt.label}</span>
                <span className="text-[10px] font-medium text-fg-subtle tabular-nums">
                  {opt.price}
                </span>
              </div>
              <p className="text-xs text-fg-muted mt-0.5 leading-snug">{opt.summary}</p>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
