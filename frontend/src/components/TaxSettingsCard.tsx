/**
 * Карточка настроек налога в /settings.
 * УСН Доходы / УСН Доходы-Расходы / ОСНО + НДС / Без налога.
 * Применяется к чистой прибыли везде в финансовых разделах.
 */
import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, CheckCircle2 } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface TaxRegime {
  code: string
  label: string
  default_rate: number
  description: string
  applies_to: string
}
interface TaxSettings {
  tax_regime: string
  tax_rate_pct: number
  vat_rate_pct: number | null
}
interface CompanySettings {
  name: string
  inn: string | null
  tax: TaxSettings
}

export function TaxSettingsCard() {
  const qc = useQueryClient()

  const { data: regimes } = useQuery<TaxRegime[]>({
    queryKey: ['tax', 'regimes'],
    queryFn: async () => (await api.get('/company/settings/regimes')).data,
    staleTime: Infinity,
  })

  const { data: settings, isLoading } = useQuery<CompanySettings>({
    queryKey: ['company', 'settings'],
    queryFn: async () => (await api.get('/company/settings/')).data,
  })

  const [regime, setRegime] = useState<string>('usn_income')
  const [rate, setRate] = useState<string>('6')
  const [vat, setVat] = useState<string>('')

  useEffect(() => {
    if (settings) {
      setRegime(settings.tax.tax_regime)
      setRate(String(settings.tax.tax_rate_pct))
      setVat(settings.tax.vat_rate_pct != null ? String(settings.tax.vat_rate_pct) : '')
    }
  }, [settings])

  const save = useMutation({
    mutationFn: async () => {
      const payload: any = {
        tax_regime: regime,
        tax_rate_pct: parseFloat(rate) || 0,
      }
      if (regime === 'osno') payload.vat_rate_pct = vat === '' ? null : parseFloat(vat) || 0
      else payload.vat_rate_pct = null
      return (await api.patch('/company/settings/', payload)).data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['company', 'settings'] }),
  })

  const dirty = !!settings && (
    regime !== settings.tax.tax_regime ||
    parseFloat(rate) !== settings.tax.tax_rate_pct ||
    (regime === 'osno' && (parseFloat(vat) || null) !== settings.tax.vat_rate_pct)
  )

  const selectedRegime = regimes?.find((r) => r.code === regime)

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-8 flex justify-center">
          <Loader2 className="w-5 h-5 animate-spin text-fg-muted" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Налоговый режим</CardTitle>
        <CardDescription>
          Применяется к расчёту <strong>чистой прибыли</strong> в P&amp;L, Cashflow, Экономике
          продаж и юнит-калькуляторе. Без налога цифры завышены.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Радио-кнопки режимов */}
        <div className="space-y-2">
          {regimes?.map((r) => (
            <label
              key={r.code}
              className={cn(
                'flex items-start gap-3 p-3 rounded-md border cursor-pointer transition-colors',
                regime === r.code
                  ? 'border-fg/40 bg-bg-subtle'
                  : 'border-border-subtle hover:bg-bg-subtle/50',
              )}
            >
              <input
                type="radio"
                name="tax_regime"
                value={r.code}
                checked={regime === r.code}
                onChange={(e) => {
                  setRegime(e.target.value)
                  setRate(String(r.default_rate))
                }}
                className="mt-0.5"
              />
              <div className="flex-1">
                <div className="font-medium text-sm">{r.label}
                  <span className="ml-2 text-xs text-fg-muted">по умолчанию {r.default_rate}%</span>
                </div>
                <div className="text-xs text-fg-muted mt-0.5">{r.description}</div>
              </div>
            </label>
          ))}
        </div>

        {/* Ставка */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-fg-muted block mb-1">Ставка %</label>
            <Input
              type="number"
              step="0.5"
              min="0"
              max="100"
              value={rate}
              onChange={(e) => setRate(e.target.value)}
            />
            {selectedRegime && (
              <p className="text-[11px] text-fg-subtle mt-1">
                База: {selectedRegime.applies_to === 'revenue' ? 'выручка' :
                       selectedRegime.applies_to === 'profit' ? 'прибыль' : 'без налога'}
              </p>
            )}
          </div>
          {regime === 'osno' && (
            <div>
              <label className="text-xs text-fg-muted block mb-1">НДС %</label>
              <Input
                type="number"
                step="1"
                min="0"
                max="100"
                placeholder="20"
                value={vat}
                onChange={(e) => setVat(e.target.value)}
              />
              <p className="text-[11px] text-fg-subtle mt-1">
                Пусто = не учитываем НДС. Стандарт: 20%, льготный 10/5/0.
              </p>
            </div>
          )}
        </div>

        {/* Сохранить */}
        <div className="flex items-center gap-3">
          <Button onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
            {save.isPending ? 'Сохраняю…' : 'Сохранить'}
          </Button>
          {save.isSuccess && !dirty && (
            <span className="text-sm text-emerald-700 inline-flex items-center gap-1">
              <CheckCircle2 className="w-4 h-4" /> Сохранено
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
