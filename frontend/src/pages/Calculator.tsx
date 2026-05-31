import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Calculator as CalcIcon } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { formatCurrency, cn } from '@/lib/utils'
import { api } from '@/lib/api'

interface CompanySettings {
  tax: { tax_regime: string; tax_rate_pct: number; vat_rate_pct: number | null }
}

interface CalcResult {
  commission_amount: number
  gross_margin: number
  op_profit: number
  tax_amount: number
  vat_amount: number
  net_margin: number
  margin_pct: number
  roi_pct: number | null
  breakeven_price: number
  customer_price: number
  spp_amount: number
  tax_regime: string
  tax_regime_label: string
  tax_rate_pct: number
  tax_base_label: string
}

/**
 * Юнит-калькулятор: ввод → backend → раскладка.
 * Налог считается на сервере через services.tax.calc_tax — правильно для всех режимов
 * (УСН Доходы / УСН Дох-Расх с мин. 1% / ОСНО с НДС).
 */
export function Calculator() {
  const [price, setPrice] = useState('5000')
  const [cost, setCost] = useState('1500')
  const [commission, setCommission] = useState('25')
  const [logistics, setLogistics] = useState('250')
  const [adSpend, setAdSpend] = useState('150')
  const [packaging, setPackaging] = useState('50')
  const [spp, setSpp] = useState('0')

  const { data: settings } = useQuery<CompanySettings>({
    queryKey: ['company', 'settings'],
    queryFn: async () => (await api.get('/company/settings/')).data,
    staleTime: Infinity,
  })

  // Debounced input — чтобы не дёргать backend на каждый символ
  const [debouncedInput, setDebouncedInput] = useState({
    price, cost, commission, logistics, adSpend, packaging, spp,
  })

  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedInput({ price, cost, commission, logistics, adSpend, packaging, spp })
    }, 250)
    return () => clearTimeout(t)
  }, [price, cost, commission, logistics, adSpend, packaging, spp])

  const { data: result, isLoading } = useQuery<CalcResult>({
    queryKey: ['calculator', debouncedInput],
    queryFn: async () => {
      const payload = {
        price: parseFloat(debouncedInput.price) || 0,
        cost: parseFloat(debouncedInput.cost) || 0,
        commission_pct: parseFloat(debouncedInput.commission) || 0,
        logistics: parseFloat(debouncedInput.logistics) || 0,
        ad_spend: parseFloat(debouncedInput.adSpend) || 0,
        packaging: parseFloat(debouncedInput.packaging) || 0,
        spp_pct: parseFloat(debouncedInput.spp) || 0,
      }
      return (await api.post('/products/calculator/calc', payload)).data
    },
    enabled: parseFloat(debouncedInput.price) > 0,
    staleTime: 60_000,
  })

  const taxLabel = settings ? {
    usn_income: 'УСН Доходы',
    usn_income_minus: 'УСН Дох-Расх',
    osno: 'ОСНО',
    none: 'Без налога',
  }[settings.tax.tax_regime] || 'налог' : 'налог'

  const taxRate = settings?.tax.tax_rate_pct ?? 0
  const priceNum = parseFloat(price) || 0

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Юнит-калькулятор</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          Считай прибыль до закупки. Налог — по режиму{' '}
          <span className="font-medium text-fg">{taxLabel}</span> ({taxRate}%),
          база: <span className="font-medium text-fg">{result?.tax_base_label ?? '…'}</span>.
          Изменить — в Настройках.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <h2 className="text-base font-semibold text-fg mb-4 flex items-center gap-2">
            <CalcIcon className="w-4 h-4 text-fg-muted" />
            Входные данные
          </h2>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Цена продавца ₽" value={price} onChange={setPrice} highlight="emerald" />
            <Field label="Себестоимость ₽" value={cost} onChange={setCost} />
            <Field label="Комиссия Ozon %" value={commission} onChange={setCommission} />
            <Field label="Логистика ₽" value={logistics} onChange={setLogistics} />
            <Field label="Упаковка ₽" value={packaging} onChange={setPackaging} />
            <Field label="Реклама ₽" value={adSpend} onChange={setAdSpend} />
            <Field label="СПП % (скидка Ozon)" value={spp} onChange={setSpp} />
          </div>
          {result && parseFloat(spp) > 0 && (
            <div className="mt-4 p-3 rounded-md bg-bg-subtle/50 border border-border-subtle">
              <div className="text-[11px] text-fg-muted uppercase tracking-wider mb-1">
                Цена для покупателя
              </div>
              <div className="flex items-baseline justify-between gap-2 text-sm">
                <span className="font-mono tabular-nums text-fg font-semibold text-base">
                  {formatCurrency(result.customer_price)}
                </span>
                <span className="text-xs text-fg-muted">
                  Ozon доплачивает {formatCurrency(result.spp_amount)}
                </span>
              </div>
              <div className="text-[11px] text-fg-muted mt-1.5">
                СПП на твою прибыль не влияет — продавец получает «Цена продавца» {formatCurrency(parseFloat(price) || 0)}.
              </div>
            </div>
          )}
        </Card>

        <Card className="p-5">
          <h2 className="text-base font-semibold text-fg mb-4">
            Расчёт {isLoading && <span className="text-xs text-fg-muted ml-2">обновление…</span>}
          </h2>
          <div className="flex flex-col gap-2 text-sm">
            <Row label="Цена" value={priceNum} positive bold />
            <Row label="− Себестоимость" value={-(parseFloat(cost) || 0)} negative />
            <Row label={`− Комиссия Ozon (${commission}%)`} value={-(result?.commission_amount ?? 0)} negative />
            <Row label="− Логистика" value={-(parseFloat(logistics) || 0)} negative />
            <Row label="− Упаковка" value={-(parseFloat(packaging) || 0)} negative />
            <Row label="ВАЛОВАЯ ПРИБЫЛЬ" value={result?.gross_margin ?? 0} subtotal />
            <Row label="− Реклама" value={-(parseFloat(adSpend) || 0)} negative />
            <Row label="ПРИБЫЛЬ ДО НАЛОГА" value={result?.op_profit ?? 0} subtotal />
            {settings?.tax.tax_regime === 'osno' && (result?.vat_amount ?? 0) > 0 && (
              <Row label={`− НДС (${settings.tax.vat_rate_pct}%)`} value={-(result?.vat_amount ?? 0)} negative />
            )}
            <Row label={`− Налог ${taxLabel} (${taxRate}%, ${result?.tax_base_label ?? '…'})`}
                 value={-(result?.tax_amount ?? 0)} negative />
            <Row label="ЧИСТАЯ ПРИБЫЛЬ" value={result?.net_margin ?? 0} subtotal />
          </div>

          <div className="grid grid-cols-3 gap-3 mt-5 pt-5 border-t border-border-subtle">
            <Metric
              label="Маржа"
              value={`${(result?.margin_pct ?? 0).toFixed(1)}%`}
              color={(result?.margin_pct ?? 0) >= 20 ? 'emerald' : (result?.margin_pct ?? 0) >= 0 ? 'amber' : 'rose'}
            />
            <Metric
              label="ROI"
              value={result?.roi_pct == null ? '—' : `${result.roi_pct.toFixed(1)}%`}
              color={
                result?.roi_pct == null ? 'fg'
                  : result.roi_pct >= 50 ? 'emerald'
                  : result.roi_pct >= 0 ? 'amber' : 'rose'
              }
            />
            <Metric
              label="Точка безубыт."
              value={result?.breakeven_price ? formatCurrency(result.breakeven_price) : '—'}
              color="fg"
            />
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
