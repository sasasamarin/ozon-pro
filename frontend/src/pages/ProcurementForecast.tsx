import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Image as ImageIcon,
  Loader2,
  Download,
  Search,
  Info,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { CostWarningBanner } from '@/components/ui/CostWarningBanner'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import { useRecommendations, ProductRecommendation } from '@/lib/recommendations'

const SIGNAL_META: Record<string, { dot: string; label: string; ring: string }> = {
  stockout: { dot: 'bg-rose-500', label: 'Стокаут — опаздываешь', ring: 'border-rose-200' },
  reorder_now: { dot: 'bg-amber-500', label: 'Пора заказывать', ring: 'border-amber-200' },
  ok: { dot: 'bg-emerald-500', label: 'Запас в норме', ring: 'border-border-subtle' },
}

function ConfidenceChip({ value }: { value: 'high' | 'medium' | 'low' }) {
  const map = {
    high: ['bg-emerald-50 text-emerald-700', 'high'],
    medium: ['bg-amber-50 text-amber-700', 'medium'],
    low: ['bg-fg-subtle/10 text-fg-muted', 'low'],
  } as const
  const [cls, label] = map[value]
  return <span className={cn('text-[10px] font-medium px-1.5 py-0.5 rounded', cls)}>{label}</span>
}

function escapeCsv(v: string | number | null | undefined): string {
  const s = v == null ? '' : String(v)
  if (s.includes(';') || s.includes('"') || s.includes('\n')) {
    return `"${s.replace(/"/g, '""')}"`
  }
  return s
}

function exportCsv(rows: ProductRecommendation[]) {
  const lines = [
    [
      'offer_id', 'name', 'остаток', 'в_пути', 'velocity_per_day',
      'buyout', 'дни_до_конца', 'точка_заказа', 'рекомендация_qty',
      'order_by', 'projected_stockout', 'сигнал', 'ABC',
      'velocity_confidence', 'buyout_confidence',
    ].join(';'),
  ]
  for (const p of rows) {
    const pr = p.procurement
    lines.push([
      escapeCsv(p.offer_id),
      escapeCsv(p.product_name),
      p.current_stock,
      p.in_transit_to_customer,
      p.velocity.adjusted_daily.toFixed(2).replace('.', ','),
      (p.buyout.rate * 100).toFixed(0) + '%',
      pr ? pr.days_left.toFixed(0) : '',
      pr ? (pr.lead_time_days + pr.safety_stock_days) : '',
      pr ? pr.recommended_qty : '',
      pr?.order_by ?? '',
      pr?.projected_stockout ?? '',
      pr?.signal ?? '',
      escapeCsv(p.abc_class),
      p.velocity.confidence,
      p.buyout.confidence,
    ].join(';'))
  }
  const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `flowoi_procurement_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export function ProcurementForecast() {
  const { data, isLoading } = useRecommendations()
  const [params] = useSearchParams()
  const highlightId = params.get('product_id')
  const [search, setSearch] = useState('')
  const [signalFilter, setSignalFilter] = useState<string>('all')

  const filtered = useMemo(() => {
    if (!data) return []
    const s = search.trim().toLowerCase()
    return data
      .filter((p) => p.procurement)
      .filter((p) => {
        if (signalFilter !== 'all' && p.procurement!.signal !== signalFilter) return false
        if (!s) return true
        return (
          p.product_name.toLowerCase().includes(s) ||
          p.offer_id.toLowerCase().includes(s)
        )
      })
      .sort((a, b) => {
        if (a.product_id === highlightId) return -1
        if (b.product_id === highlightId) return 1
        return (a.procurement!.days_left ?? 99999) - (b.procurement!.days_left ?? 99999)
      })
  }, [data, search, signalFilter, highlightId])

  const missingCount = useMemo(() => {
    if (!data) return 0
    return data.filter((p) => p.cost_price == null || p.cost_price === 100).length
  }, [data])

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Прогноз закупок</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            {data ? `${data.length} товаров · рекомендации обновляются автоматически` : 'Загрузка…'}
          </p>
        </div>
        <Button onClick={() => exportCsv(filtered)} variant="secondary">
          <Download className="w-4 h-4" /> CSV
        </Button>
      </div>

      <CostWarningBanner count={missingCount} context="romi" />

      <Card className="p-4 flex items-start gap-3 bg-blue-50/60 border-blue-200/60">
        <Info className="w-5 h-5 text-blue-700 mt-0.5 shrink-0" />
        <div className="text-sm text-blue-900/90">
          Параметры поставки (lead_time, MOQ) пока не введены. Используются дефолты:
          lead_time = 14 дней, safety = 7 дней, MOQ = 1. После заполнения параметров — точка заказа
          и рекомендуемое количество пересчитаются.
        </div>
      </Card>

      <Card className="p-4 flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[220px]">
          <label className="block text-[11px] font-medium text-fg-muted uppercase tracking-wider mb-1">
            Поиск
          </label>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-fg-subtle" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="название или offer_id"
              className="pl-9"
            />
          </div>
        </div>
        <div className="flex gap-2">
          {(['all', 'stockout', 'reorder_now', 'ok'] as const).map((k) => (
            <button
              key={k}
              onClick={() => setSignalFilter(k)}
              className={cn(
                'px-3 py-1.5 rounded-md text-sm border transition-colors',
                signalFilter === k
                  ? 'border-fg bg-fg text-bg'
                  : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
              )}
            >
              {k === 'all' && 'Все'}
              {k === 'stockout' && '🔴 Стокаут'}
              {k === 'reorder_now' && '🟡 Пора заказывать'}
              {k === 'ok' && '🟢 В норме'}
            </button>
          ))}
        </div>
      </Card>

      {isLoading ? (
        <Card className="py-16 flex justify-center items-center text-fg-muted">
          <Loader2 className="w-5 h-5 animate-spin mr-2" /> Считаем рекомендации…
        </Card>
      ) : filtered.length === 0 ? (
        <Card className="py-16 flex justify-center items-center text-fg-muted text-sm">
          Нет товаров под фильтр
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((p) => {
            const pr = p.procurement!
            const meta = SIGNAL_META[pr.signal] || SIGNAL_META.ok
            const highlighted = p.product_id === highlightId
            const reorderPoint = pr.lead_time_days + pr.safety_stock_days
            return (
              <Card
                key={p.product_id}
                className={cn(
                  'p-4 flex flex-col gap-3 border-2 transition-colors',
                  meta.ring,
                  highlighted && 'ring-2 ring-indigo-400 ring-offset-2',
                )}
              >
                {/* Header */}
                <div className="flex items-start gap-3">
                  {p.image_url ? (
                    <img
                      src={p.image_url}
                      alt=""
                      className="w-12 h-12 rounded object-cover shrink-0 border border-border-subtle"
                    />
                  ) : (
                    <div className="w-12 h-12 rounded bg-bg-subtle flex items-center justify-center shrink-0">
                      <ImageIcon className="w-5 h-5 text-fg-subtle" />
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-fg text-sm leading-snug line-clamp-2">
                      {p.product_name}
                    </div>
                    <div className="text-xs text-fg-muted font-mono mt-0.5">
                      {p.offer_id}
                    </div>
                  </div>
                  {p.abc_class && (
                    <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700">
                      {p.abc_class}
                    </span>
                  )}
                </div>

                {/* Signal */}
                <div className="flex items-center gap-2 text-sm">
                  <span className={cn('inline-block w-2 h-2 rounded-full', meta.dot)} />
                  <span className="font-medium text-fg">{meta.label}</span>
                </div>

                {/* Stats */}
                <div className="grid grid-cols-2 gap-y-2 gap-x-3 text-xs">
                  <Stat
                    label="Остаток"
                    value={formatNumber(p.current_stock)}
                    sub={p.in_transit_to_customer > 0 ? `+${p.in_transit_to_customer} в пути` : undefined}
                  />
                  <Stat
                    label="Дни до конца"
                    value={Number.isFinite(pr.days_left) ? pr.days_left.toFixed(0) : '∞'}
                    accent={pr.signal === 'stockout' ? 'red' : pr.signal === 'reorder_now' ? 'amber' : undefined}
                  />
                  <Stat
                    label="Скорость/день"
                    value={p.velocity.adjusted_daily.toFixed(1)}
                    confidence={p.velocity.confidence}
                    sub={`x${p.velocity.multiplier.toFixed(1)} (${p.velocity.days_in_stock}/${p.velocity.window_days}д)`}
                  />
                  <Stat
                    label="Выкупаемость"
                    value={(p.buyout.rate * 100).toFixed(0) + '%'}
                    confidence={p.buyout.confidence}
                    sub={`${p.buyout.sample_size} заказов`}
                  />
                  <Stat
                    label="Точка заказа"
                    value={`${reorderPoint} дн.`}
                    sub={`lead ${pr.lead_time_days} + safety ${pr.safety_stock_days}`}
                  />
                  <Stat
                    label="Заказать"
                    value={pr.recommended_qty > 0 ? formatNumber(pr.recommended_qty) : '—'}
                    sub={pr.order_by ? `до ${pr.order_by.slice(0, 10)}` : undefined}
                  />
                </div>

                {/* Basis tooltip-text */}
                {pr.basis && (
                  <details className="text-xs text-fg-muted">
                    <summary className="cursor-pointer hover:text-fg select-none">Почему так</summary>
                    <p className="mt-1.5 leading-relaxed">{pr.basis}</p>
                  </details>
                )}

                {/* Warnings */}
                {pr.warnings.length > 0 && (
                  <ul className="text-xs text-amber-700 list-disc list-inside space-y-0.5">
                    {pr.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                )}

                {/* No-profit hint без cost */}
                {(p.cost_price == null || p.cost_price === 100) && (
                  <div className="text-xs text-fg-muted bg-bg-subtle/60 rounded px-2 py-1.5">
                    Себестоимость не введена — прибыль/ROI не считаются.
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}

interface StatProps {
  label: string
  value: string
  sub?: string
  accent?: 'red' | 'amber'
  confidence?: 'high' | 'medium' | 'low'
}

function Stat({ label, value, sub, accent, confidence }: StatProps) {
  return (
    <div>
      <div className="text-[10px] font-medium text-fg-muted uppercase tracking-wider">{label}</div>
      <div className="flex items-baseline gap-1.5">
        <span
          className={cn(
            'text-sm font-semibold tabular-nums',
            accent === 'red' && 'text-rose-700',
            accent === 'amber' && 'text-amber-700',
            !accent && 'text-fg',
          )}
        >
          {value}
        </span>
        {confidence && <ConfidenceChip value={confidence} />}
      </div>
      {sub && <div className="text-[10px] text-fg-subtle">{sub}</div>}
    </div>
  )
}
