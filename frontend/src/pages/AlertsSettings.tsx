/**
 * /alerts/settings — настройки правил алертов.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings as SettingsIcon, Plus, Trash2, ToggleLeft, ToggleRight } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface Rule {
  id: string; marker_type: string; is_active: boolean
  threshold_json: Record<string, any>; quiet_hours_json: any
  channels_json: string[]; ozon_account_id: string | null
}

const TYPE_LABEL: Record<string, string> = {
  stockout: 'Кончается товар (порог: дней до 0)',
  overstock: 'Затоварен (порог: дней покрытия)',
  margin_below_min: 'Маржа ниже мин. % (порог: %)',
  price_below_cost: 'Цена ниже с/с (без параметров)',
  credit_payment_due: 'Платёж по кредиту скоро (порог: дней)',
  negative_review: 'Негативный отзыв (порог: рейтинг ≤)',
  sales_drop: 'Падение продаж (порог: % падения)',
  return_received: 'Возврат получен',
  cashflow_gap: 'Кассовый разрыв',
  fbs_not_shipped: 'FBS не отгружен (порог: часов)',
  tax_due: 'Срок налога (порог: дней до)',
  rating_drop: 'Рейтинг ниже (порог: рейтинг)',
  ad_budget_exceeded: 'ДРР выше нормы (порог: %)',
  position_drop: 'Падение позиции (порог: на сколько ↑)',
  low_conversion: 'Низкая конверсия в корзину (порог: %)',
  competitor_dump: 'Демпинг конкурентов (color_index=RED)',
  commission_change: 'Изменение комиссии (порог: дней ретроспективы)',
}

const ALL_TYPES = Object.keys(TYPE_LABEL)
const CHANNELS = ['in_app', 'telegram', 'email', 'webhook']

export function AlertsSettings() {
  const qc = useQueryClient()
  const [newType, setNewType] = useState('stockout')

  const { data: rules = [] } = useQuery<Rule[]>({
    queryKey: ['alert-rules'],
    queryFn: async () => (await api.get('/alerts/rules')).data,
  })

  const update = useMutation({
    mutationFn: async ({ id, ...p }: any) => (await api.patch(`/alerts/rules/${id}`, p)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alert-rules'] }),
  })
  const create = useMutation({
    mutationFn: async (p: any) => (await api.post('/alerts/rules', p)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alert-rules'] }),
  })
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/alerts/rules/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alert-rules'] }),
  })
  const seed = useMutation({
    mutationFn: async () => (await api.post('/alerts/seed-defaults')).data,
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ['alert-rules'] })
      alert(`Создано дефолтных правил: ${d.created}`)
    },
  })

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
          <SettingsIcon className="w-6 h-6 text-blue-500" />
          Настройки маркеров и алертов
        </h1>
        <p className="text-sm text-fg-muted mt-1">
          Какие события и пороги отслеживаются. Выкл = не срабатывает.
        </p>
      </div>

      {rules.length === 0 && (
        <Card className="p-4 bg-blue-50/30 border-blue-200 text-sm flex items-center justify-between">
          <span>Правил ещё нет. Создать набор по умолчанию?</span>
          <Button onClick={() => seed.mutate()} disabled={seed.isPending}>
            Создать дефолты
          </Button>
        </Card>
      )}

      <Card className="p-4 space-y-3">
        <h3 className="text-sm font-semibold">Добавить правило</h3>
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label className="text-xs text-fg-muted">Тип</label>
            <select value={newType} onChange={(e) => setNewType(e.target.value)}
                    className="w-full px-2 py-1 border border-border-subtle rounded text-sm bg-bg">
              {ALL_TYPES.map((t) => (
                <option key={t} value={t} disabled={rules.some((r) => r.marker_type === t)}>
                  {TYPE_LABEL[t]}{rules.some((r) => r.marker_type === t) ? ' — уже есть' : ''}
                </option>
              ))}
            </select>
          </div>
          <Button onClick={() => create.mutate({ marker_type: newType, channels_json: ['in_app'] })}
                  disabled={create.isPending}
                  className="inline-flex items-center gap-1">
            <Plus className="w-4 h-4" /> Добавить
          </Button>
        </div>
      </Card>

      <div className="space-y-3">
        {rules.map((r) => (
          <Card key={r.id} className="p-4">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="flex-1 min-w-[280px]">
                <div className="text-sm font-semibold text-fg">{TYPE_LABEL[r.marker_type] || r.marker_type}</div>
                <div className="mt-2 grid grid-cols-2 md:grid-cols-3 gap-2">
                  {/* Threshold fields */}
                  {r.marker_type === 'stockout' && (
                    <ThField label="Дней до 0" value={r.threshold_json.days_left ?? 7}
                             onSave={(v) => update.mutate({ id: r.id, threshold_json: { days_left: +v } })} />
                  )}
                  {r.marker_type === 'overstock' && (
                    <ThField label="Дней покрытия" value={r.threshold_json.days_left ?? 180}
                             onSave={(v) => update.mutate({ id: r.id, threshold_json: { days_left: +v } })} />
                  )}
                  {r.marker_type === 'margin_below_min' && (
                    <ThField label="Мин. % маржи" value={r.threshold_json.min_pct ?? 10}
                             onSave={(v) => update.mutate({ id: r.id, threshold_json: { min_pct: +v } })} />
                  )}
                  {r.marker_type === 'credit_payment_due' && (
                    <ThField label="Предупредить за дней" value={r.threshold_json.days_before ?? 7}
                             onSave={(v) => update.mutate({ id: r.id, threshold_json: { days_before: +v } })} />
                  )}
                  {r.marker_type === 'negative_review' && (
                    <ThField label="Рейтинг ≤" value={r.threshold_json.rating_max ?? 3}
                             onSave={(v) => update.mutate({ id: r.id, threshold_json: { rating_max: +v } })} />
                  )}
                  {r.marker_type === 'sales_drop' && (
                    <ThField label="% падения" value={r.threshold_json.drop_pct ?? 30}
                             onSave={(v) => update.mutate({ id: r.id, threshold_json: { drop_pct: +v } })} />
                  )}
                  {r.marker_type === 'fbs_not_shipped' && (
                    <ThField label="Часов до алерта" value={r.threshold_json.hours_threshold ?? 24}
                             onSave={(v) => update.mutate({ id: r.id, threshold_json: { hours_threshold: +v } })} />
                  )}
                  {r.marker_type === 'tax_due' && (
                    <ThField label="Дней до срока" value={r.threshold_json.days_before ?? 14}
                             onSave={(v) => update.mutate({ id: r.id, threshold_json: { days_before: +v } })} />
                  )}
                  {r.marker_type === 'rating_drop' && (
                    <ThField label="Мин. рейтинг" value={r.threshold_json.min_rating ?? 4.5}
                             onSave={(v) => update.mutate({ id: r.id, threshold_json: { min_rating: +v } })} />
                  )}
                  {r.marker_type === 'ad_budget_exceeded' && (
                    <ThField label="Макс. ДРР %" value={r.threshold_json.drr_pct_max ?? 25}
                             onSave={(v) => update.mutate({ id: r.id, threshold_json: { drr_pct_max: +v } })} />
                  )}
                  {r.marker_type === 'position_drop' && (
                    <ThField label="Падение на N позиций" value={r.threshold_json.position_drop ?? 5}
                             onSave={(v) => update.mutate({ id: r.id, threshold_json: { position_drop: +v } })} />
                  )}
                  {r.marker_type === 'low_conversion' && (
                    <ThField label="Мин. конверсия %" value={r.threshold_json.min_pct ?? 5}
                             onSave={(v) => update.mutate({ id: r.id, threshold_json: { min_pct: +v } })} />
                  )}
                  {r.marker_type === 'commission_change' && (
                    <ThField label="Ретроспектива (дней)" value={r.threshold_json.lookback_days ?? 30}
                             onSave={(v) => update.mutate({ id: r.id, threshold_json: { lookback_days: +v } })} />
                  )}
                </div>

                {/* Channels */}
                <div className="mt-3">
                  <div className="text-xs text-fg-muted mb-1">Каналы доставки</div>
                  <div className="flex gap-1 flex-wrap">
                    {CHANNELS.map((ch) => {
                      const on = r.channels_json.includes(ch)
                      return (
                        <button key={ch}
                          onClick={() => update.mutate({
                            id: r.id,
                            channels_json: on
                              ? r.channels_json.filter((c) => c !== ch)
                              : [...r.channels_json, ch],
                          })}
                          className={cn('text-[10px] px-2 py-0.5 rounded border',
                            on ? 'bg-blue-100 border-blue-300 text-blue-700'
                               : 'bg-bg-subtle text-fg-muted border-border-subtle')}>
                          {ch}
                        </button>
                      )
                    })}
                  </div>
                </div>
              </div>

              <div className="flex flex-col items-end gap-2">
                <button onClick={() => update.mutate({ id: r.id, is_active: !r.is_active })}
                        className="inline-flex items-center gap-1 text-sm">
                  {r.is_active ? (
                    <><ToggleRight className="w-6 h-6 text-emerald-600" /><span className="text-emerald-700">Вкл</span></>
                  ) : (
                    <><ToggleLeft className="w-6 h-6 text-fg-muted" /><span className="text-fg-muted">Выкл</span></>
                  )}
                </button>
                <button onClick={() => {
                  if (confirm(`Удалить правило «${TYPE_LABEL[r.marker_type] || r.marker_type}»?`)) {
                    remove.mutate(r.id)
                  }
                }} className="p-1 hover:bg-rose-100 rounded">
                  <Trash2 className="w-4 h-4 text-rose-600" />
                </button>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}

function ThField({ label, value, onSave }: { label: string; value: number; onSave: (v: string) => void }) {
  const [val, setVal] = useState(String(value))
  return (
    <div>
      <label className="text-xs text-fg-muted">{label}</label>
      <input type="number" value={val}
             onChange={(e) => setVal(e.target.value)}
             onBlur={() => +val !== value && onSave(val)}
             className="w-full px-2 py-1 border border-border-subtle rounded text-sm bg-bg" />
    </div>
  )
}
