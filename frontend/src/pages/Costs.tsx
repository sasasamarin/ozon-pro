import { useState, useMemo, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Tags,
  Search,
  Download,
  Upload,
  Loader2,
  Save,
  X,
  Image as ImageIcon,
  CheckCircle2,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api, API_BASE_URL } from '@/lib/api'
import { formatCurrency, cn } from '@/lib/utils'

interface CostRow {
  product_id: string
  offer_id: string
  name: string
  cabinet_id: string
  cabinet_name: string
  image_url: string | null
  purchase_price: number | null
  delivery_to_wh: number | null
  packaging: number | null
  other_costs: number | null
  full_cost: number | null
  confidence: 'exact' | 'estimated' | 'missing' | null
  source: string | null
  effective_from: string | null
}

interface ImportResult {
  total_rows: number
  matched: number
  pending_saved: number
  failed: number
  errors: string[]
}

function ConfidenceBadge({ value }: { value: string | null }) {
  if (!value) return <span className="text-fg-subtle text-xs">—</span>
  const map: Record<string, [string, string]> = {
    exact: ['bg-emerald-50 text-emerald-700', 'точная'],
    estimated: ['bg-amber-50 text-amber-700', 'приблиз.'],
    missing: ['bg-rose-50 text-rose-700', 'заглушка'],
  }
  const [cls, label] = map[value] ?? ['bg-bg-subtle text-fg-muted', value]
  return (
    <span className={cn('text-[11px] font-medium px-1.5 py-0.5 rounded', cls)}>
      {label}
    </span>
  )
}

type Filter = 'all' | 'missing' | 'estimated' | 'exact'

export function Costs() {
  const qc = useQueryClient()
  const [filter, setFilter] = useState<Filter>('all')
  const [search, setSearch] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data, isLoading } = useQuery<CostRow[]>({
    queryKey: ['costs', 'list'],
    queryFn: async () => {
      const res = await api.get('/costs/products')
      return res.data
    },
  })

  const filtered = useMemo(() => {
    if (!data) return []
    let rows = data
    if (filter !== 'all') {
      rows = rows.filter((r) => (r.confidence ?? 'missing') === filter)
    }
    const s = search.trim().toLowerCase()
    if (s) {
      rows = rows.filter(
        (r) => r.name.toLowerCase().includes(s) || r.offer_id.toLowerCase().includes(s),
      )
    }
    return rows
  }, [data, filter, search])

  const counts = useMemo(() => {
    const acc = { all: 0, exact: 0, estimated: 0, missing: 0 }
    for (const r of data ?? []) {
      acc.all++
      const c = (r.confidence ?? 'missing') as keyof typeof acc
      acc[c]++
    }
    return acc
  }, [data])

  const downloadTemplate = async () => {
    const res = await fetch(`${API_BASE_URL}/costs/template.csv`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('flowoi_token') || ''}` },
    })
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'flowoi_costs_template.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  const uploadCSV = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      const res = await api.post('/costs/upload-csv', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60000,
      })
      return res.data as ImportResult
    },
    onSuccess: (data) => {
      setImportResult(data)
      qc.invalidateQueries({ queryKey: ['costs', 'list'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      qc.invalidateQueries({ queryKey: ['pnl'] })
      qc.invalidateQueries({ queryKey: ['recommendations'] })
    },
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    uploadCSV.mutate(file)
    e.target.value = ''
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Себестоимость</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            {counts.all} товаров · точных {counts.exact} · приблиз. {counts.estimated} · заглушек {counts.missing}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={downloadTemplate}>
            <Download className="w-4 h-4" /> Шаблон
          </Button>
          <Button
            variant="secondary"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadCSV.isPending}
          >
            {uploadCSV.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Upload className="w-4 h-4" />
            )}
            Загрузить CSV
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            onChange={handleFileChange}
            className="hidden"
          />
        </div>
      </div>

      {importResult && (
        <Card className="p-4 flex items-start gap-3 bg-emerald-50/60 border-emerald-200">
          <CheckCircle2 className="w-5 h-5 text-emerald-700 mt-0.5 shrink-0" />
          <div className="flex-1 text-sm">
            <p className="font-semibold text-emerald-900">
              CSV импортирован: {importResult.total_rows} строк
            </p>
            <p className="text-emerald-800 mt-0.5">
              Применено к товарам: <strong>{importResult.matched}</strong> ·
              В очередь (pending): <strong>{importResult.pending_saved}</strong>
              {importResult.failed > 0 && (
                <> · С ошибками: <strong>{importResult.failed}</strong></>
              )}
            </p>
            {importResult.errors.length > 0 && (
              <ul className="mt-2 text-xs text-emerald-800/80 list-disc list-inside space-y-0.5">
                {importResult.errors.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            )}
          </div>
          <button
            onClick={() => setImportResult(null)}
            className="text-emerald-700 hover:text-emerald-900"
          >
            <X className="w-4 h-4" />
          </button>
        </Card>
      )}

      {/* Filters */}
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
          {(['all', 'missing', 'estimated', 'exact'] as Filter[]).map((k) => (
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
              {k === 'missing' && `Заглушки (${counts.missing})`}
              {k === 'estimated' && `Приблиз. (${counts.estimated})`}
              {k === 'exact' && `Точные (${counts.exact})`}
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
                  <th className="py-2.5 px-4 font-medium">кабинет</th>
                  <th className="py-2.5 px-4 font-medium text-right">себестоимость</th>
                  <th className="py-2.5 px-4 font-medium text-right">+логистика+упак</th>
                  <th className="py-2.5 px-4 font-medium text-right">итог</th>
                  <th className="py-2.5 px-4 font-medium">статус</th>
                  <th className="py-2.5 px-4 font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {filtered.map((r) => (
                  <CostTableRow
                    key={r.product_id}
                    row={r}
                    editing={editingId === r.product_id}
                    onEdit={() => setEditingId(r.product_id)}
                    onCancel={() => setEditingId(null)}
                    onSaved={() => {
                      setEditingId(null)
                      qc.invalidateQueries({ queryKey: ['costs', 'list'] })
                      qc.invalidateQueries({ queryKey: ['dashboard'] })
                      qc.invalidateQueries({ queryKey: ['pnl'] })
                      qc.invalidateQueries({ queryKey: ['recommendations'] })
                    }}
                  />
                ))}
              </tbody>
            </table>
            {filtered.length === 0 && (
              <div className="py-12 flex flex-col items-center text-fg-muted">
                <Tags className="w-8 h-8 mb-2 text-fg-subtle" />
                <p className="text-sm">Нет товаров под фильтр</p>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  )
}

function CostTableRow({
  row, editing, onEdit, onCancel, onSaved,
}: {
  row: CostRow
  editing: boolean
  onEdit: () => void
  onCancel: () => void
  onSaved: () => void
}) {
  const [purchase, setPurchase] = useState(row.purchase_price?.toString() ?? '')
  const [delivery, setDelivery] = useState(row.delivery_to_wh?.toString() ?? '0')
  const [packaging, setPackaging] = useState(row.packaging?.toString() ?? '0')
  const [other, setOther] = useState(row.other_costs?.toString() ?? '0')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  const save = async () => {
    setSaving(true)
    setErr('')
    try {
      await api.post(`/costs/products/${row.product_id}`, {
        purchase_price: parseFloat(purchase || '0'),
        delivery_to_wh: parseFloat(delivery || '0'),
        packaging: parseFloat(packaging || '0'),
        other_costs: parseFloat(other || '0'),
      })
      onSaved()
    } catch (e: unknown) {
      setErr('Ошибка сохранения')
      setSaving(false)
    }
  }

  if (editing) {
    return (
      <tr className="bg-indigo-50/30">
        <td className="py-2.5 px-4">
          <div className="flex items-center gap-3 min-w-0">
            {row.image_url ? (
              <img src={row.image_url} alt="" className="w-9 h-9 rounded object-cover shrink-0 border border-border-subtle" />
            ) : (
              <div className="w-9 h-9 rounded bg-bg-subtle flex items-center justify-center shrink-0">
                <ImageIcon className="w-4 h-4 text-fg-subtle" />
              </div>
            )}
            <div className="min-w-0">
              <div className="font-medium text-fg truncate max-w-[260px]">{row.name}</div>
              <div className="text-xs text-fg-muted font-mono truncate">{row.offer_id}</div>
            </div>
          </div>
        </td>
        <td className="py-2.5 px-4 text-fg-muted">{row.cabinet_name}</td>
        <td className="py-2.5 px-2">
          <Input value={purchase} onChange={(e) => setPurchase(e.target.value)} type="number" step="any" className="w-24 text-right" />
        </td>
        <td className="py-2.5 px-2">
          <div className="flex gap-1">
            <Input value={delivery} onChange={(e) => setDelivery(e.target.value)} type="number" step="any" placeholder="лог" className="w-16 text-right" />
            <Input value={packaging} onChange={(e) => setPackaging(e.target.value)} type="number" step="any" placeholder="упак" className="w-16 text-right" />
            <Input value={other} onChange={(e) => setOther(e.target.value)} type="number" step="any" placeholder="др" className="w-16 text-right" />
          </div>
        </td>
        <td className="py-2.5 px-4 text-right tabular-nums font-semibold text-fg">
          {formatCurrency(
            (parseFloat(purchase || '0') || 0) +
              (parseFloat(delivery || '0') || 0) +
              (parseFloat(packaging || '0') || 0) +
              (parseFloat(other || '0') || 0),
          )}
        </td>
        <td className="py-2.5 px-4">
          <ConfidenceBadge value="exact" />
        </td>
        <td className="py-2.5 px-2">
          <div className="flex gap-1">
            <button
              onClick={save}
              disabled={saving}
              className="p-1.5 rounded text-emerald-700 hover:bg-emerald-100"
              title="Сохранить"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            </button>
            <button onClick={onCancel} className="p-1.5 rounded text-fg-muted hover:bg-bg-subtle">
              <X className="w-4 h-4" />
            </button>
          </div>
          {err && <div className="text-xs text-rose-700 mt-1">{err}</div>}
        </td>
      </tr>
    )
  }

  return (
    <tr className="hover:bg-bg-subtle/40 cursor-pointer" onClick={onEdit}>
      <td className="py-2.5 px-4">
        <div className="flex items-center gap-3 min-w-0">
          {row.image_url ? (
            <img src={row.image_url} alt="" className="w-9 h-9 rounded object-cover shrink-0 border border-border-subtle" />
          ) : (
            <div className="w-9 h-9 rounded bg-bg-subtle flex items-center justify-center shrink-0">
              <ImageIcon className="w-4 h-4 text-fg-subtle" />
            </div>
          )}
          <div className="min-w-0">
            <div className="font-medium text-fg truncate max-w-[260px]">{row.name}</div>
            <div className="text-xs text-fg-muted font-mono truncate">{row.offer_id}</div>
          </div>
        </div>
      </td>
      <td className="py-2.5 px-4 text-fg-muted">{row.cabinet_name}</td>
      <td className="py-2.5 px-4 text-right tabular-nums">
        {row.purchase_price != null ? formatCurrency(row.purchase_price) : '—'}
      </td>
      <td className="py-2.5 px-4 text-right tabular-nums text-fg-muted text-xs">
        {row.delivery_to_wh || row.packaging || row.other_costs
          ? `+${formatCurrency((row.delivery_to_wh ?? 0) + (row.packaging ?? 0) + (row.other_costs ?? 0))}`
          : '—'}
      </td>
      <td className="py-2.5 px-4 text-right tabular-nums font-semibold">
        {row.full_cost != null ? formatCurrency(row.full_cost) : '—'}
      </td>
      <td className="py-2.5 px-4">
        <ConfidenceBadge value={row.confidence} />
      </td>
      <td className="py-2.5 px-4 text-fg-subtle text-xs">правка →</td>
    </tr>
  )
}
