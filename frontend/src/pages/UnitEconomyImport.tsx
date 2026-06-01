/**
 * /finance/unit-economy/import — загрузка XLSX «Экономика магазина → Общие расходы».
 *
 * Поток:
 * 1. Выбираем кабинет + файл → POST /preview → видим что прилетело
 * 2. Если сверка с формулой Ozon ОК → кнопка «Загрузить» → POST /commit
 * 3. Иначе показываем строки с расхождением — юзер решает как чинить
 */
import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Upload, CheckCircle2, AlertTriangle, FileSpreadsheet, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import type { OzonAccountSummary } from '@/stores/cabinet'

interface RowSummary {
  sku: number
  offer_id: string | null
  name: string | null
  delivered_qty: number | null
  returned_qty: number | null
  revenue: number | null
  spp_points: number | null
  ozon_commission: number | null
  storage: number | null
  ozon_profit: number | null
  computed_profit: number
  diff: number
  sverka_ok: boolean
}

interface UploadStatus {
  cabinet_id: string
  cabinet_name: string
  month: string
  period_from: string
  period_to: string
  imported_at: string
  sku_count: number
}

interface PreviewResp {
  cabinet_id: string
  cabinet_name: string
  period_from: string
  period_to: string
  month: string
  file_name: string
  rows_count: number
  skipped_rows: number
  unknown_columns: string[]
  total_revenue: number
  total_spp_points: number
  total_partner_programs: number
  total_seller_revenue: number
  total_ozon_profit: number
  total_computed_profit: number
  sverka_pass_count: number
  sverka_fail_count: number
  sample_rows: RowSummary[]
}

export function UnitEconomyImport() {
  const { data: cabinets = [] } = useQuery<OzonAccountSummary[]>({
    queryKey: ['ozon-accounts'],
    queryFn: async () => (await api.get('/ozon-accounts/')).data,
    staleTime: 5 * 60_000,
  })

  // Какие XLSX уже загружены — для подписи рядом с каждым кабинетом
  const { data: uploadStatus = [] } = useQuery<UploadStatus[]>({
    queryKey: ['unit-economy-status'],
    queryFn: async () => (await api.get('/finance/unit-economy/status')).data,
    staleTime: 60_000,
  })
  // Карта: cabinet_id → [{month, imported_at, sku}, ...]
  const statusByCabinet = uploadStatus.reduce<Record<string, UploadStatus[]>>((acc, s) => {
    if (!acc[s.cabinet_id]) acc[s.cabinet_id] = []
    acc[s.cabinet_id].push(s)
    return acc
  }, {})

  const [cabinetId, setCabinetId] = useState<string>('')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<PreviewResp | null>(null)
  const [committed, setCommitted] = useState<{ rows_written: number; month: string } | null>(null)

  const previewMut = useMutation({
    mutationFn: async () => {
      if (!file || !cabinetId) throw new Error('Выбери кабинет и файл')
      const fd = new FormData()
      fd.append('file', file)
      fd.append('cabinet_id', cabinetId)
      const res = await api.post<PreviewResp>('/finance/unit-economy/preview', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60_000,
      })
      return res.data
    },
    onSuccess: setPreview,
  })

  const commitMut = useMutation({
    mutationFn: async () => {
      if (!file || !cabinetId) throw new Error('Нет файла')
      const fd = new FormData()
      fd.append('file', file)
      fd.append('cabinet_id', cabinetId)
      const res = await api.post('/finance/unit-economy/commit', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60_000,
      })
      return res.data
    },
    onSuccess: (data) => setCommitted({ rows_written: data.rows_written, month: data.month }),
  })

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">
          Импорт «Экономика магазина» (XLSX)
        </h1>
        <p className="text-sm text-fg-muted mt-1.5 max-w-2xl">
          Загрузи выгрузку из Ozon: <strong>Финансы → Экономика магазина → Общие расходы → Экспорт XLSX</strong>.
          Точное «зеркало Ozon»: storage / реклама / эквайринг per-товар, как в кабинете.
          Эти данные публичный API не отдаёт.
        </p>
      </div>

      <Card className="p-5 max-w-3xl">
        <div className="grid gap-4">
          <div>
            <label className="block text-xs font-medium text-fg-muted uppercase tracking-wider mb-1.5">
              Кабинет
            </label>
            <select
              value={cabinetId}
              onChange={(e) => setCabinetId(e.target.value)}
              className="w-full h-10 px-3 rounded-md border border-border-subtle bg-bg text-sm"
            >
              <option value="">— выбери кабинет —</option>
              {cabinets.map((c) => {
                const uploads = statusByCabinet[c.id] || []
                const recent = uploads.slice(0, 2)
                  .map((u) => {
                    const monthLabel = new Date(u.month).toLocaleDateString('ru', {
                      month: 'long', year: 'numeric',
                    })
                    const importedDate = new Date(u.imported_at).toLocaleDateString('ru', {
                      day: '2-digit', month: '2-digit',
                    })
                    return `${monthLabel} (загр. ${importedDate})`
                  }).join(', ')
                return (
                  <option key={c.id} value={c.id}>
                    {c.name}{recent ? ` — XLSX: ${recent}` : ' — XLSX не загружен'}
                  </option>
                )
              })}
            </select>
            <p className="text-[11px] text-fg-subtle mt-1">
              XLSX от Ozon не содержит cabinet_id — указываем явно. Рядом видно когда последний раз грузили какой месяц.
            </p>
          </div>

          <div>
            <label className="block text-xs font-medium text-fg-muted uppercase tracking-wider mb-1.5">
              XLSX файл
            </label>
            <label className={cn(
              'flex items-center gap-2 h-10 px-3 rounded-md border border-dashed cursor-pointer transition-colors text-sm',
              file ? 'border-emerald-400 bg-emerald-50/40 text-emerald-900' : 'border-border-subtle hover:bg-bg-subtle text-fg-muted',
            )}>
              <FileSpreadsheet className="w-4 h-4" />
              <span className="truncate">{file?.name || 'выбери .xlsx файл'}</span>
              <input
                type="file"
                accept=".xlsx,.xlsm"
                className="hidden"
                onChange={(e) => { setFile(e.target.files?.[0] || null); setPreview(null); setCommitted(null) }}
              />
            </label>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => previewMut.mutate()}
              disabled={!file || !cabinetId || previewMut.isPending}
              className="h-10 px-4 rounded-md bg-fg text-bg text-sm font-medium disabled:opacity-50 inline-flex items-center gap-1.5"
            >
              {previewMut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
              Превью
            </button>
            {previewMut.isError && (
              <span className="text-xs text-rose-700">
                {(previewMut.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
                  || String(previewMut.error)}
              </span>
            )}
          </div>
        </div>
      </Card>

      {preview && (
        <Card className="p-5">
          <h2 className="text-lg font-semibold text-fg mb-4">Превью загрузки</h2>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5 text-sm">
            <Kv label="Кабинет" value={preview.cabinet_name} />
            <Kv label="Период" value={`${preview.period_from} → ${preview.period_to}`} />
            <Kv label="SKU в файле" value={String(preview.rows_count)} />
            <Kv label="Пропущено строк" value={String(preview.skipped_rows)} />
            <Kv label="Выручка" value={formatCurrency(preview.total_revenue)} />
            <Kv label="Баллы за скидки" value={formatCurrency(preview.total_spp_points)} bold />
            <Kv label="Программы партнёров" value={formatCurrency(preview.total_partner_programs)} />
            <Kv label="Выручка продавца" value={formatCurrency(preview.total_seller_revenue)} bold accent />
            <Kv label="Прибыль (Ozon)" value={formatCurrency(preview.total_ozon_profit)} />
            <Kv label="Прибыль (наша формула)" value={formatCurrency(preview.total_computed_profit)} />
          </div>

          <div className={cn(
            'rounded-md border px-4 py-3 mb-4 text-sm flex items-start gap-2',
            preview.sverka_fail_count === 0
              ? 'border-emerald-300 bg-emerald-50/60 text-emerald-900'
              : 'border-amber-300 bg-amber-50/60 text-amber-900',
          )}>
            {preview.sverka_fail_count === 0
              ? <CheckCircle2 className="w-4 h-4 mt-0.5 flex-shrink-0" />
              : <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />}
            <div>
              <strong>Сверка формулы прибыли:</strong>{' '}
              {preview.sverka_pass_count} из {preview.rows_count} строк сходятся с Ozon
              {preview.sverka_fail_count > 0 && (
                <span> · {preview.sverka_fail_count} расхождений — проверь маппинг колонок</span>
              )}
            </div>
          </div>

          {preview.unknown_columns.length > 0 && (
            <div className="rounded-md border border-amber-300 bg-amber-50/60 px-4 py-3 mb-4 text-xs">
              <strong>Неизвестные колонки в файле:</strong>{' '}
              {preview.unknown_columns.join(' · ')}
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-bg-subtle/50 border-b border-border-subtle">
                <tr className="text-left text-fg-muted">
                  <th className="py-1.5 px-2">SKU</th>
                  <th className="py-1.5 px-2">Артикул</th>
                  <th className="py-1.5 px-2">Товар</th>
                  <th className="py-1.5 px-2 text-right">Доставлено</th>
                  <th className="py-1.5 px-2 text-right">Возврат</th>
                  <th className="py-1.5 px-2 text-right">Выручка</th>
                  <th className="py-1.5 px-2 text-right">Баллы</th>
                  <th className="py-1.5 px-2 text-right">Комиссия</th>
                  <th className="py-1.5 px-2 text-right">Хранение</th>
                  <th className="py-1.5 px-2 text-right">Прибыль Ozon</th>
                  <th className="py-1.5 px-2 text-right">Прибыль наша</th>
                  <th className="py-1.5 px-2 text-right">Δ</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {preview.sample_rows.map((r) => (
                  <tr key={r.sku} className={cn('hover:bg-bg-subtle/40', !r.sverka_ok && 'bg-amber-50/50')}>
                    <td className="py-1.5 px-2 font-mono text-[10px]">{r.sku}</td>
                    <td className="py-1.5 px-2 font-mono text-[10px]">{r.offer_id}</td>
                    <td className="py-1.5 px-2 truncate max-w-[180px]" title={r.name || ''}>{r.name}</td>
                    <td className="py-1.5 px-2 text-right">{formatNumber(r.delivered_qty || 0)}</td>
                    <td className="py-1.5 px-2 text-right">{formatNumber(r.returned_qty || 0)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{formatCurrency(r.revenue || 0)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{formatCurrency(r.spp_points || 0)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums text-rose-700">{formatCurrency(r.ozon_commission || 0)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums text-rose-700">{formatCurrency(r.storage || 0)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums font-semibold">{formatCurrency(r.ozon_profit || 0)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{formatCurrency(r.computed_profit)}</td>
                    <td className={cn('py-1.5 px-2 text-right tabular-nums', r.sverka_ok ? 'text-emerald-700' : 'text-rose-700 font-bold')}>
                      {r.diff.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-5 flex items-center gap-3">
            <button
              onClick={() => commitMut.mutate()}
              disabled={commitMut.isPending || committed !== null}
              className="h-10 px-5 rounded-md bg-emerald-600 text-white text-sm font-medium disabled:opacity-50 inline-flex items-center gap-1.5"
            >
              {commitMut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
              {committed ? 'Загружено' : `Сохранить в БД (${preview.rows_count} SKU)`}
            </button>
            {committed && (
              <span className="text-sm text-emerald-700">
                ✓ Записано {committed.rows_written} строк за {committed.month}
              </span>
            )}
          </div>
        </Card>
      )}
    </div>
  )
}

function Kv({ label, value, bold, accent }: { label: string; value: string; bold?: boolean; accent?: boolean }) {
  return (
    <div>
      <div className="text-[11px] text-fg-muted uppercase tracking-wider">{label}</div>
      <div className={cn(
        'tabular-nums mt-0.5',
        bold ? 'text-base font-semibold' : 'text-sm',
        accent && 'text-emerald-700',
      )}>{value}</div>
    </div>
  )
}
