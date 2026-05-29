import { useMemo, useState } from 'react'
import { Calculator as CalcIcon, Save } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { formatCurrency, cn } from '@/lib/utils'

/** Юнит-калькулятор: цена → себестоимость → комиссия → логистика → прибыль */
export function Calculator() {
  const [price, setPrice] = useState('5000')
  const [cost, setCost] = useState('1500')
  const [commission, setCommission] = useState('25')
  const [logistics, setLogistics] = useState('250')
  const [adSpend, setAdSpend] = useState('150')
  const [packaging, setPackaging] = useState('50')
  const [tax, setTax] = useState('6')

  const result = useMemo(() => {
    const p = parseFloat(price) || 0
    const c = parseFloat(cost) || 0
    const commPct = parseFloat(commission) || 0
    const lg = parseFloat(logistics) || 0
    const ad = parseFloat(adSpend) || 0
    const pk = parseFloat(packaging) || 0
    const tx = parseFloat(tax) || 0

    const commAmount = p * commPct / 100
    const taxAmount = p * tx / 100
    const grossMargin = p - c - commAmount - lg - pk
    const netMargin = grossMargin - ad - taxAmount
    const marginPct = p > 0 ? (netMargin / p) * 100 : 0
    const roi = c > 0 ? (netMargin / c) * 100 : 0
    const breakeven = (c + lg + pk + ad) / (1 - commPct / 100 - tx / 100)

    return { commAmount, taxAmount, grossMargin, netMargin, marginPct, roi, breakeven }
  }, [price, cost, commission, logistics, adSpend, packaging, tax])

  const r = result

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Юнит-калькулятор</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          Считай прибыль до того как закупать. Все значения в рублях.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <h2 className="text-base font-semibold text-fg mb-4 flex items-center gap-2">
            <CalcIcon className="w-4 h-4 text-fg-muted" />
            Входные данные
          </h2>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Цена продажи ₽" value={price} onChange={setPrice} highlight="emerald" />
            <Field label="Себестоимость ₽" value={cost} onChange={setCost} />
            <Field label="Комиссия Ozon %" value={commission} onChange={setCommission} />
            <Field label="Логистика ₽" value={logistics} onChange={setLogistics} />
            <Field label="Упаковка ₽" value={packaging} onChange={setPackaging} />
            <Field label="Реклама ₽" value={adSpend} onChange={setAdSpend} />
            <Field label="Налог УСН %" value={tax} onChange={setTax} />
          </div>
        </Card>

        <Card className="p-5">
          <h2 className="text-base font-semibold text-fg mb-4">Расчёт</h2>
          <div className="flex flex-col gap-2 text-sm">
            <Row label="Цена" value={parseFloat(price) || 0} positive bold />
            <Row label="− Себестоимость" value={-(parseFloat(cost) || 0)} negative />
            <Row label={`− Комиссия Ozon (${commission}%)`} value={-r.commAmount} negative />
            <Row label="− Логистика" value={-(parseFloat(logistics) || 0)} negative />
            <Row label="− Упаковка" value={-(parseFloat(packaging) || 0)} negative />
            <Row label="ВАЛОВАЯ ПРИБЫЛЬ" value={r.grossMargin} subtotal />
            <Row label="− Реклама" value={-(parseFloat(adSpend) || 0)} negative />
            <Row label={`− Налог УСН (${tax}%)`} value={-r.taxAmount} negative />
            <Row label="ЧИСТАЯ ПРИБЫЛЬ" value={r.netMargin} subtotal />
          </div>

          <div className="grid grid-cols-3 gap-3 mt-5 pt-5 border-t border-border-subtle">
            <Metric label="Маржа" value={`${r.marginPct.toFixed(1)}%`} color={r.marginPct >= 20 ? 'emerald' : r.marginPct >= 0 ? 'amber' : 'rose'} />
            <Metric label="ROI" value={`${r.roi.toFixed(1)}%`} color={r.roi >= 50 ? 'emerald' : r.roi >= 0 ? 'amber' : 'rose'} />
            <Metric label="Точка безубыт." value={formatCurrency(r.breakeven)} color="fg" />
          </div>
        </Card>
      </div>
    </div>
  )
}

function Field({
  label, value, onChange, highlight,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  highlight?: 'emerald'
}) {
  return (
    <div>
      <label className="block text-[11px] font-medium text-fg-muted uppercase tracking-wider mb-1">{label}</label>
      <Input value={value} onChange={(e) => onChange(e.target.value)} type="number" step="any" className={cn(
        'text-right tabular-nums',
        highlight === 'emerald' && 'border-emerald-300 bg-emerald-50/30',
      )} />
    </div>
  )
}

function Row({
  label, value, positive, negative, subtotal, bold,
}: {
  label: string
  value: number
  positive?: boolean
  negative?: boolean
  subtotal?: boolean
  bold?: boolean
}) {
  return (
    <div className={cn(
      'flex justify-between',
      subtotal && 'pt-2 mt-1 border-t border-border-subtle font-semibold text-base',
    )}>
      <span className={cn(
        'text-fg-muted',
        bold && 'font-medium text-fg',
        subtotal && 'text-fg uppercase tracking-wider text-xs',
      )}>{label}</span>
      <span className={cn(
        'font-mono tabular-nums',
        positive && 'text-emerald-700',
        negative && 'text-rose-700',
        subtotal && (value >= 0 ? 'text-emerald-700' : 'text-rose-700'),
      )}>
        {formatCurrency(value)}
      </span>
    </div>
  )
}

function Metric({ label, value, color }: { label: string; value: string; color: 'emerald' | 'amber' | 'rose' | 'fg' }) {
  const cls = {
    emerald: 'text-emerald-700',
    amber: 'text-amber-700',
    rose: 'text-rose-700',
    fg: 'text-fg',
  }[color]
  return (
    <div className="text-center">
      <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">{label}</p>
      <p className={cn('text-[20px] font-semibold mt-1 tabular-nums', cls)}>{value}</p>
    </div>
  )
}
