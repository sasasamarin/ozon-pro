import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Truck,
  Search,
  Loader2,
  Save,
  X,
  Image as ImageIcon,
  CheckCircle2,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api } from '@/lib/api'
import { cn, formatNumber } from '@/lib/utils'

interface SupplyRow {
  product_id: string
  offer_id: string
  name: string
  cabinet_name: string
  lead_time_total_days: number
  lead_time_production_days: number | null
  lead_time_delivery_days: number | null
  lead_time_processing_days: number | null
  moq: number
  batch_step: number
  batch_strict: boolean
  safety_stock_days: number
  longterm_window_days: number
  shortterm_window_days: number
  forecast_strategy: string
  has_record: boolean
}

type Filter = 'all' | 'configured' | 'defaults'

export function SupplyParams() {
  const qc = useQueryClient()
  const [filter, setFilter] = useState<Filter>('all')
  const [search, setSearch] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)

  const { data, isLoading } = useQuery<SupplyRow[]>({
    queryKey: ['supply-params', 'list'],
    queryFn: async () => (await api.get('/supply-params/')).data,
  })

  const filtered = useMemo(() => {
    if (!data) return []
    let rows = data
    if (filter === 'configured') rows = rows.filter((r) => r.has_record)
    if (filter === 'defaults') rows = rows.filter((r) => !r.has_record)
    const s = search.trim().toLowerCase()
    if (s) {
      rows = rows.filter(
        (r) => r.name.toLowerCase().includes(s) || r.offer_id.toLowerCase().includes(s),
      )
    }
    return rows
  }, [data, filter, search])

  const counts = useMemo(() => {
    const acc = { all: 0, configured: 0, defaults: 0 }
    for (const r of data ?? []) {
      acc.all++
      if (r.has_record) acc.configured++
      else acc.defaults++
    }
    return acc
  }, [data])

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Параметры поставки</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          {counts.all} товаров · настроены {counts.configured} · дефолты {counts.defaults}
        </p>
      </div>

      <Card className="p-4 flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[240px]">
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
          {(['all', 'defaults', 'configured'] as Filter[]).map((k) => (
            <button
              key={k}
              onClick={() => setFilter(k)}
              className={cn(
                'px-3 py-1.5 rounded-md text-sm border transition-colors',
                filter === k
                  ? 'border-fg bg-fg text-bg'
                  : 'border-border-subtle text-fg-muted hover:bg-bg-subtle hover:text-fg',
              )}
            >
              {k === 'all' && `Все (${counts.all})`}
              {k === 'defaults' && `Дефолты (${counts.defaults})`}
              {k === 'configured' && `Настроены (${counts.configured})`}
            </button>
          ))}
        </div>
      </Card>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 flex justify-center items-center text-fg-muted">
            <Loader2 className="w-5 h-5 animate-spin mr-2" /> Загрузка…
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                  <th className="py-2.5 px-4 font-medium">товар</th>
                  <th className="py-2.5 px-4 font-medium text-right">lead time</th>
                  <th className="py-2.5 px-4 font-medium text-right">страх. запас</th>
                  <th className="py-2.5 px-4 font-medium text-right">MOQ</th>
                  <th className="py-2.5 px-4 font-medium text-right">кратность</th>
                  <th className="py-2.5 px-4 font-medium">источник</th>
                  <th className="py-2.5 px-4 font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {filtered.map((r) => (
                  <SupplyRowComponent
                    key={r.product_id}
                    row={r}
                    editing={editingId === r.product_id}
                    onEdit={() => setEditingId(r.product_id)}
                    onCancel={() => setEditingId(null)}
                    onSaved={() => {
                      setEditingId(null)
                      qc.invalidateQueries({ queryKey: ['supply-params', 'list'] })
                      qc.invalidateQueries({ queryKey: ['recommendations'] })
                    }}
                  />
                ))}
              </tbody>
            </table>
            {filtered.length === 0 && (
              <div className="py-12 flex flex-col items-center text-fg-muted">
                <Truck className="w-8 h-8 mb-2 text-fg-subtle" />
                <p className="text-sm">Нет товаров под фильтр</p>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  )
}

function SupplyRowComponent({
  row, editing, onEdit, onCancel, onSaved,
}: {
  row: SupplyRow
  editing: boolean
  onEdit: () => void
  onCancel: () => void
  onSaved: () => void
}) {
  const [leadTotal, setLeadTotal] = useState(row.lead_time_total_days.toString())
  const [leadProd, setLeadProd] = useState((row.lead_time_production_days ?? '').toString())
  const [leadDeliv, setLeadDeliv] = useState((row.lead_time_delivery_days ?? '').toString())
  const [leadProc, setLeadProc] = useState((row.lead_time_processing_days ?? '').toString())
  const [moq, setMoq] = useState(row.moq.toString())
  const [step, setStep] = useState(row.batch_step.toString())
  const [strict, setStrict] = useState(row.batch_strict)
  const [safety, setSafety] = useState(row.safety_stock_days.toString())
  const [saving, setSaving] = useState(false)

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        lead_time_total_days: parseInt(leadTotal || '0', 10),
        lead_time_production_days: leadProd ? parseInt(leadProd, 10) : null,
        lead_time_delivery_days: leadDeliv ? parseInt(leadDeliv, 10) : null,
        lead_time_processing_days: leadProc ? parseInt(leadProc, 10) : null,
        moq: parseInt(moq || '1', 10),
        batch_step: parseInt(step || '1', 10),
        batch_strict: strict,
        safety_stock_days: parseInt(safety || '0', 10),
        longterm_window_days: row.longterm_window_days,
        shortterm_window_days: row.shortterm_window_days,
        forecast_strategy: row.forecast_strategy,
      }
      const res = await api.post(`/supply-params/${row.product_id}`, body)
      return res.data
    },
    onSuccess: () => {
      setSaving(false)
      onSaved()
    },
    onError: () => setSaving(false),
  })

  const onSave = () => {
    setSaving(true)
    save.mutate()
  }

  if (editing) {
    return (
      <tr className="bg-indigo-50/30">
        <td className="py-2.5 px-4">
          <div className="min-w-0">
            <div className="font-medium text-fg truncate max-w-[260px]">{row.name}</div>
            <div className="text-xs text-fg-muted font-mono truncate">{row.offer_id}</div>
            <div className="text-[10px] text-fg-subtle mt-0.5">{row.cabinet_name}</div>
          </div>
        </td>
        <td className="py-2.5 px-2">
          <div className="flex flex-col gap-1">
            <Input value={leadTotal} onChange={(e) => setLeadTotal(e.target.value)} type="number" placeholder="всего" className="w-20 text-right" />
            <div className="flex gap-1 text-[10px]">
              <Input value={leadProd} onChange={(e) => setLeadProd(e.target.value)} type="number" placeholder="пр-во" className="w-14 text-right !text-xs !h-7" />
              <Input value={leadDeliv} onChange={(e) => setLeadDeliv(e.target.value)} type="number" placeholder="дост" className="w-14 text-right !text-xs !h-7" />
              <Input value={leadProc} onChange={(e) => setLeadProc(e.target.value)} type="number" placeholder="обр" className="w-14 text-right !text-xs !h-7" />
            </div>
          </div>
        </td>
        <td className="py-2.5 px-2">
          <Input value={safety} onChange={(e) => setSafety(e.target.value)} type="number" className="w-20 text-right" />
        </td>
        <td className="py-2.5 px-2">
          <Input value={moq} onChange={(e) => setMoq(e.target.value)} type="number" className="w-20 text-right" />
        </td>
        <td className="py-2.5 px-2">
          <div className="flex flex-col gap-1">
            <Input value={step} onChange={(e) => setStep(e.target.value)} type="number" className="w-20 text-right" />
            <label className="flex items-center gap-1 text-[10px] text-fg-muted">
              <input type="checkbox" checked={strict} onChange={(e) => setStrict(e.target.checked)} className="w-3 h-3" />
              строгая
            </label>
          </div>
        </td>
        <td className="py-2.5 px-4 text-xs text-fg-muted">manual</td>
        <td className="py-2.5 px-2">
          <div className="flex gap-1">
            <button onClick={onSave} disabled={saving} className="p-1.5 rounded text-emerald-700 hover:bg-emerald-100">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            </button>
            <button onClick={onCancel} className="p-1.5 rounded text-fg-muted hover:bg-bg-subtle">
              <X className="w-4 h-4" />
            </button>
          </div>
        </td>
      </tr>
    )
  }

  return (
    <tr className="hover:bg-bg-subtle/40 cursor-pointer" onClick={onEdit}>
      <td className="py-2.5 px-4">
        <div className="min-w-0">
          <div className="font-medium text-fg truncate max-w-[280px]">{row.name}</div>
          <div className="text-xs text-fg-muted font-mono truncate">{row.offer_id}</div>
          <div className="text-[10px] text-fg-subtle mt-0.5">{row.cabinet_name}</div>
        </div>
      </td>
      <td className="py-2.5 px-4 text-right tabular-nums">
        {row.lead_time_total_days} <span className="text-xs text-fg-subtle">дн</span>
      </td>
      <td className="py-2.5 px-4 text-right tabular-nums">
        {row.safety_stock_days} <span className="text-xs text-fg-subtle">дн</span>
      </td>
      <td className="py-2.5 px-4 text-right tabular-nums">{formatNumber(row.moq)}</td>
      <td className="py-2.5 px-4 text-right tabular-nums">
        {formatNumber(row.batch_step)}
        {row.batch_strict && <span className="text-[10px] text-fg-subtle ml-1">строгая</span>}
      </td>
      <td className="py-2.5 px-4">
        {row.has_record ? (
          <span className="text-[11px] font-medium px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700">
            настроен
          </span>
        ) : (
          <span className="text-[11px] font-medium px-1.5 py-0.5 rounded bg-fg-subtle/10 text-fg-muted">
            дефолт
          </span>
        )}
      </td>
      <td className="py-2.5 px-4 text-fg-subtle text-xs">правка →</td>
    </tr>
  )
}
