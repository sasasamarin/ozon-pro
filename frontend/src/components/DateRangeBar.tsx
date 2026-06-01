/**
 * Унифицированный date-range пикер для всех страниц.
 *
 * Возвращает `days` (число), но поддерживает 3 режима выбора:
 *   - Пресеты: 7 / 28 / 30 / 90 / 365 дней
 *   - «Месяц»: выпадающий список последних 12 месяцев. Выбираем месяц →
 *     рассчитываем days = (сегодня - первое число месяца) + 1.
 *   - «Свободно»: 2 date input → days = (сегодня - date_from).
 *
 * Эндпоинты у нас принимают `days` (или `date_from/date_to` опционально).
 * Если в будущем переключаемся на date_from/date_to — будет одна точка правки.
 */
import { useState } from 'react'
import { cn } from '@/lib/utils'

interface Props {
  days: number
  onChange: (days: number) => void
  /** Какие пресеты показать. По умолчанию [7, 28, 30, 90, 365]. */
  presets?: number[]
  className?: string
}

const PRESET_LABEL: Record<number, string> = {
  7: '7д', 28: '28д', 30: '30д', 90: '90д', 180: '180д', 365: 'Год',
}

function monthsBack(n: number): { value: string; label: string; days: number }[] {
  const out: { value: string; label: string; days: number }[] = []
  const today = new Date()
  const MONTH_RU = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек']
  for (let i = 0; i < n; i++) {
    const d = new Date(today.getFullYear(), today.getMonth() - i, 1)
    const value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    const label = `${MONTH_RU[d.getMonth()]} ${d.getFullYear()}`
    const days = Math.ceil((today.getTime() - d.getTime()) / 86400000) + 1
    out.push({ value, label, days })
  }
  return out
}

export function DateRangeBar({
  days, onChange,
  presets = [7, 28, 30, 90, 365],
  className,
}: Props) {
  const [mode, setMode] = useState<'preset' | 'month' | 'custom'>('preset')
  const [month, setMonth] = useState<string>('')
  const [from, setFrom] = useState<string>('')
  const [to, setTo] = useState<string>('')
  const months = monthsBack(12)

  const handleMonthChange = (v: string) => {
    setMonth(v)
    const m = months.find(x => x.value === v)
    if (m) onChange(m.days)
  }

  const handleCustomApply = () => {
    if (!from) return
    const d1 = new Date(from)
    const d2 = to ? new Date(to) : new Date()
    const daysCalc = Math.max(1, Math.round((d2.getTime() - d1.getTime()) / 86400000) + 1)
    onChange(daysCalc)
  }

  return (
    <div className={cn('flex flex-wrap gap-2 items-center', className)}>
      <div className="flex gap-1.5">
        {presets.map((d) => (
          <button key={d} onClick={() => { setMode('preset'); onChange(d) }}
                  className={cn(
                    'px-3 py-1.5 rounded-md text-sm border transition-colors',
                    mode === 'preset' && days === d
                      ? 'border-fg bg-fg text-bg'
                      : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
                  )}>
            {PRESET_LABEL[d] || `${d}д`}
          </button>
        ))}
      </div>
      <div className="flex gap-1.5 items-center">
        <select value={mode === 'month' ? month : ''}
                onChange={(e) => { setMode('month'); handleMonthChange(e.target.value) }}
                className={cn(
                  'px-2 py-1.5 rounded-md text-sm border bg-bg',
                  mode === 'month' ? 'border-fg' : 'border-border-subtle text-fg-muted',
                )}>
          <option value="">Месяц…</option>
          {months.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
        </select>
        <button onClick={() => setMode('custom')}
                className={cn(
                  'px-3 py-1.5 rounded-md text-sm border transition-colors',
                  mode === 'custom'
                    ? 'border-fg bg-fg text-bg'
                    : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
                )}>
          Свободно
        </button>
      </div>
      {mode === 'custom' && (
        <div className="flex gap-1.5 items-center text-xs">
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)}
                 className="px-2 py-1 border border-border-subtle rounded bg-bg" />
          <span className="text-fg-muted">…</span>
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)}
                 className="px-2 py-1 border border-border-subtle rounded bg-bg" />
          <button onClick={handleCustomApply}
                  disabled={!from}
                  className="px-2 py-1 bg-accent text-white rounded text-xs hover:bg-accent-hover disabled:opacity-50">
            Применить
          </button>
        </div>
      )}
    </div>
  )
}
