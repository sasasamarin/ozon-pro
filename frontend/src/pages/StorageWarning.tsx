/**
 * /analytics/storage-warning — алерты «не попасть на хранение».
 *
 * Каждый SKU имеет вердикт 🔴/🟡/🟢:
 *  - 🔴 действовать: мёртвый сток или хранение > 20% выручки
 *  - 🟡 следить: запас > 60 дней или хранение > 5% выручки
 *  - 🟢 норма
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle, Package, TrendingDown, Loader2, Info, Lightbulb,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { AskAIButton } from '@/components/AskAIButton'
import { api } from '@/lib/api'
import { useCabinetStore } from '@/stores/cabinet'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'

type Verdict = 'red' | 'yellow' | 'green' | 'no_data'

interface WarningItem {
  product_id: string
  name: string | null
  offer_id: string | null
  ozon_sku: number | null
  cabinet_name: string
  current_stock: number
  daily_velocity: number | null
  days_of_inventory: number | null
  storage_30d_rub: number
  revenue_30d_rub: number
  storage_share_pct: number | null
  verdict: Verdict
  reason: string
  recommendation: string
  mode: 'A_live' | 'B_dead' | 'unknown'
}

interface WarningResp {
  items: WarningItem[]
  summary: {
    counts: Record<Verdict, number>
    total_storage_30d_rub: number
    thresholds: Record<string, number>
    note: string
  }
}

const VERDICT_STYLE: Record<Verdict, { color: string; label: string; emoji: string }> = {
  red: { color: 'bg-rose-50 text-rose-700 border-rose-200', label: 'Действовать', emoji: '🔴' },
  yellow: { color: 'bg-amber-50 text-amber-700 border-amber-200', label: 'Следить', emoji: '🟡' },
  green: { color: 'bg-emerald-50 text-emerald-700 border-emerald-200', label: 'Норма', emoji: '🟢' },
  no_data: { color: 'bg-gray-50 text-gray-600 border-gray-200', label: 'Нет данных', emoji: '⚪' },
}

export function StorageWarning() {
  const { selectedCabinetIds } = useCabinetStore()
  const cabinetId = selectedCabinetIds[0] || null
  const [onlyProblematic, setOnlyProblematic] = useState(true)

  const { data, isLoading } = useQuery<WarningResp>({
    queryKey: ['storage-warning', cabinetId, onlyProblematic],
    queryFn: async () => {
      const params = new URLSearchParams({ only_problematic: String(onlyProblematic) })
      if (cabinetId) params.append('cabinet_id', cabinetId)
      return (await api.get(`/storage-warning/?${params.toString()}`)).data
    },
  })

  const items = data?.items || []
  const summary = data?.summary

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
            <AlertTriangle className="w-6 h-6 text-amber-500" />
            Не попасть на хранение
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            Каждый SKU оценён: <b className="text-rose-700">🔴 действовать</b>{' '}
            (мёртвый сток или хранение «съедает» маржу), <b className="text-amber-700">🟡 следить</b>{' '}
            (запас &gt; 60 дней или хранение &gt; 5% выручки), <b className="text-emerald-700">🟢 норма</b>.
          </p>
        </div>
        <AskAIButton
          context={{
            type: 'table',
            source_page: 'storage-warning',
            source_label: 'Хранение по SKU (последние 30 дней)',
            metrics: ['storage_30d_rub', 'days_of_inventory', 'storage_share_pct', 'daily_velocity'],
            cabinet_id: cabinetId || undefined,
            cabinet_ids: selectedCabinetIds,
          }}
          question="Какие SKU кандидаты на распродажу/вывод и почему?"
          variant="solid"
        />
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <SummaryCard label="🔴 Действовать" count={summary.counts.red} tone="rose" />
          <SummaryCard label="🟡 Следить" count={summary.counts.yellow} tone="amber" />
          <SummaryCard label="🟢 Норма" count={summary.counts.green} tone="emerald" />
          <SummaryCard label="⚪ Нет данных" count={summary.counts.no_data} tone="gray" />
          <Card className="p-3">
            <div className="text-xs text-fg-muted">Хранение за 30 дней</div>
            <div className="text-lg font-semibold text-fg mt-0.5 tabular-nums">
              {formatCurrency(summary.total_storage_30d_rub)}
            </div>
            <div className="text-xs text-fg-muted mt-0.5">факт из Ozon Report API</div>
          </Card>
        </div>
      )}

      {/* Filter toggle */}
      <Card className="p-3 flex items-center justify-between text-sm">
        <label className="inline-flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={onlyProblematic}
            onChange={(e) => setOnlyProblematic(e.target.checked)}
            className="rounded"
          />
          <span>Показать только 🔴 и 🟡</span>
        </label>
        <span className="text-xs text-fg-muted">
          Показано {items.length} SKU{summary && !onlyProblematic ? ` из ${Object.values(summary.counts).reduce((a, b) => a + b, 0)}` : ''}
        </span>
      </Card>

      {summary?.note && (
        <Card className="p-3 bg-blue-50/40 border-blue-200 text-xs text-blue-900 flex items-start gap-2">
          <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          {summary.note}
        </Card>
      )}

      {/* Table */}
      <Card className="overflow-x-auto">
        {isLoading ? (
          <div className="p-6 flex justify-center">
            <Loader2 className="w-5 h-5 animate-spin text-fg-muted" />
          </div>
        ) : items.length === 0 ? (
          <div className="p-6 text-center text-sm text-fg-muted">
            🎉 Проблем не найдено. Если фильтр включён — попробуй снять «только 🔴/🟡».
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-xs text-fg-muted bg-bg-subtle/30">
              <tr>
                <th className="py-2 px-3 text-left">SKU</th>
                <th className="py-2 px-3 text-center">Вердикт</th>
                <th className="py-2 px-3 text-right">Остаток</th>
                <th className="py-2 px-3 text-right">Дней<br />запаса</th>
                <th className="py-2 px-3 text-right">Хранение 30д</th>
                <th className="py-2 px-3 text-right">Выручка 30д</th>
                <th className="py-2 px-3 text-right">% от выручки</th>
                <th className="py-2 px-3 text-left">Что делать</th>
              </tr>
            </thead>
            <tbody>
              {items.map((i) => {
                const v = VERDICT_STYLE[i.verdict]
                return (
                  <tr key={i.product_id} className="border-t border-border-subtle/50 hover:bg-bg-subtle/20">
                    <td className="py-2 px-3 max-w-[260px]">
                      <div className="text-fg truncate" title={i.name || ''}>
                        {i.name?.slice(0, 50)}
                      </div>
                      <div className="text-[11px] text-fg-muted">
                        {i.offer_id} · {i.cabinet_name}
                      </div>
                    </td>
                    <td className="py-2 px-3 text-center">
                      <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs', v.color)}>
                        {v.emoji} {v.label}
                      </span>
                      {i.mode === 'B_dead' && (
                        <div className="text-[10px] text-rose-600 mt-0.5 flex items-center justify-center gap-0.5">
                          <TrendingDown className="w-3 h-3" /> мёртвый сток
                        </div>
                      )}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums">
                      {formatNumber(i.current_stock)}
                      {i.daily_velocity !== null && (
                        <div className="text-[10px] text-fg-muted">
                          {i.daily_velocity.toFixed(2)} шт/день
                        </div>
                      )}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums">
                      {i.days_of_inventory !== null ? `${i.days_of_inventory.toFixed(0)}` : '—'}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums">
                      {formatCurrency(i.storage_30d_rub)}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums">
                      {formatCurrency(i.revenue_30d_rub)}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums">
                      {i.storage_share_pct !== null
                        ? <span className={cn(
                            i.storage_share_pct > 20 && 'text-rose-700 font-semibold',
                            i.storage_share_pct > 5 && i.storage_share_pct <= 20 && 'text-amber-700',
                          )}>{i.storage_share_pct.toFixed(1)}%</span>
                        : '—'
                      }
                    </td>
                    <td className="py-2 px-3 max-w-[280px]">
                      <div className="text-xs text-fg" title={i.reason}>{i.reason}</div>
                      <div className="text-xs text-fg-muted mt-1 flex items-start gap-1">
                        <Lightbulb className="w-3 h-3 text-amber-500 mt-0.5 shrink-0" />
                        {i.recommendation}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}


function SummaryCard({ label, count, tone }: { label: string; count: number; tone: string }) {
  const toneClass = {
    rose: 'text-rose-700',
    amber: 'text-amber-700',
    emerald: 'text-emerald-700',
    gray: 'text-gray-600',
  }[tone] || 'text-fg'
  return (
    <Card className="p-3">
      <div className="text-xs text-fg-muted">{label}</div>
      <div className={cn('text-2xl font-semibold mt-0.5 tabular-nums', toneClass)}>{count}</div>
    </Card>
  )
}
