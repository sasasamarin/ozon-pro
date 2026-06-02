/**
 * Унифицированный date-range пикер с ТОЧНЫМИ датами.
 *
 * Раньше возвращал только `days` — это приводило к расхождениям при
 * выборе «Месяц/Свободно»: days=31 от сегодня = 31 день назад, а нужно
 * точный диапазон.
 *
 * Теперь возвращает:
 *   { days, dateFrom, dateTo }
 *  где dateFrom/dateTo = ISO 'YYYY-MM-DD' (точные границы).
 *
 * Пресет (7д/28д/30д/90д/Год) → dateFrom = today − N + 1, dateTo = today.
 * Месяц → точные границы выбранного месяца.
 * Свободно → как ввёл юзер.
 *
 * Старые места используют только `days` — продолжают работать.
 * Новые места: используют dateFrom/dateTo для точной агрегации.
 */
import { useState, useEffect } from 'react'
import { cn } from '@/lib/utils'

export interface DateRange {
  days: number
  dateFrom: string  // ISO 'YYYY-MM-DD'
  dateTo: string
}

interface Props {
  days: number
  onChange: (range: DateRange) => void
  presets?: number[]
  className?: string
}

const PRESET_LABEL: Record<number, string> = {
  7: '7д', 28: '28д', 30: '30д', 90: '90д', 180: '180д', 365: 'Год',
}

const MONTH_RU = ['янв', 'фев', 'мар', 'апр', 'май', 'июн',
                  'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function rangeFromDays(days: number): DateRange {
  const to = new Date()
  const from = new Date()
  from.setDate(to.getDate() - days + 1)
  return { days, dateFrom: iso(from), dateTo: iso(to) }
}

function rangeFromMonth(value: string): DateRange {
  // value = "2026-05"
  const [yy, mm] = value.split('-').map(Number)
  const from = new Date(yy, mm - 1, 1)
  const to = new Date(yy, mm, 0)  // последний день месяца
  const days = Math.round((to.getTime() - from.getTime()) / 86400000) + 1
  return { days, dateFrom: iso(from), dateTo: iso(to) }
}

function rangeFromCustom(from: string, to: string): DateRange {
  if (!from) return rangeFromDays(30)
  const d1 = new Date(from)
  const d2 = to ? new Date(to) : new Date()
  const days = Math.max(1, Math.round((d2.getTime() - d1.getTime()) / 86400000) + 1)
  return { days, dateFrom: from, dateTo: to || iso(d2) }
}

function monthsBack(n: number): { value: string; label: string }[] {
  const out: { value: string; label: string }[] = []
  const today = new Date()
  for (let i = 0; i < n; i++) {
    const d = new Date(today.getFullYear(), today.getMonth() - i, 1)
    out.push({
      value: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`,
      label: `${MONTH_RU[d.getMonth()]} ${d.getFullYear()}`,
    })
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

  const setPreset = (d: number) => { setMode('preset'); onChange(rangeFromDays(d)) }
  const setMonthMode = (v: string) => { setMode('month'); setMonth(v); onChange(rangeFromMonth(v)) }
  const setCustomMode = () => {
    setMode('custom')
    if (from) onChange(rangeFromCustom(from, to))
  }
  const applyCustom = () => onChange(rangeFromCustom(from, to))

  return (
    <div className={cn('flex flex-wrap gap-2 items-center', className)}>
      <div className="flex gap-1.5">
        {presets.map((d) => (
          <button key={d} onClick={() => setPreset(d)}
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
                onChange={(e) => setMonthMode(e.target.value)}
                className={cn(
                  'px-2 py-1.5 rounded-md text-sm border bg-bg',
                  mode === 'month' ? 'border-fg' : 'border-border-subtle text-fg-muted',
                )}>
          <option value="">Месяц…</option>
          {months.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
        </select>
        <button onClick={setCustomMode}
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
          <button onClick={applyCustom} disabled={!from}
                  className="px-2 py-1 bg-accent text-white rounded text-xs hover:bg-accent-hover disabled:opacity-50">
            Применить
          </button>
        </div>
      )}
    </div>
  )
}
