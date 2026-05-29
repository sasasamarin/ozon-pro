import { useQuery } from '@tanstack/react-query'
import { Landmark, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatCurrency, cn } from '@/lib/utils'

interface CreditRow {
  id: string
  product_type: string
  product_type_label: string
  cabinet_name: string
  principal: number
  interest_rate: number | null
  issued_at: string
  due_date: string | null
  status: string
  current_debt: number
}

interface CreditSummary {
  total_active_debt: number
  total_pnl_interest: number
  items: CreditRow[]
}

const STATUS_META: Record<string, { label: string; cls: string }> = {
  active: { label: 'Активен', cls: 'bg-emerald-50 text-emerald-700' },
  repaying: { label: 'Погашается', cls: 'bg-amber-50 text-amber-700' },
  closed: { label: 'Закрыт', cls: 'bg-fg-subtle/10 text-fg-muted' },
}

export function Credit() {
  const { data, isLoading } = useQuery<CreditSummary>({
    queryKey: ['credit', 'list'],
    queryFn: async () => (await api.get('/credit/list')).data,
  })

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Кредиты и финансирование</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          Все финансовые продукты Ozon: авансы, кредиты, рассрочки
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Card className="p-5 border-2 border-rose-200 bg-rose-50/30">
          <p className="text-[11px] uppercase text-fg-muted">Активный долг</p>
          <p className="text-2xl font-semibold text-rose-700 mt-1 tabular-nums">
            {formatCurrency(data?.total_active_debt ?? 0)}
          </p>
        </Card>
        <Card className="p-5">
          <p className="text-[11px] uppercase text-fg-muted">Проценты в P&L (всего)</p>
          <p className="text-2xl font-semibold text-fg mt-1 tabular-nums">
            {formatCurrency(data?.total_pnl_interest ?? 0)}
          </p>
        </Card>
      </div>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 flex justify-center"><Loader2 className="w-5 h-5 animate-spin" /></div>
        ) : (data?.items.length ?? 0) === 0 ? (
          <div className="py-12 flex flex-col items-center text-fg-muted text-sm">
            <Landmark className="w-8 h-8 mb-2 text-fg-subtle" />
            <p>Финансовых продуктов нет.</p>
            <p className="text-xs mt-1">Подключи Ozon-кредитование в кабинете продавца — данные подтянутся автоматически.</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-bg-subtle/50 border-b border-border-subtle">
              <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
                <th className="py-2.5 px-4 font-medium">тип</th>
                <th className="py-2.5 px-4 font-medium">кабинет</th>
                <th className="py-2.5 px-4 font-medium">выдан</th>
                <th className="py-2.5 px-4 font-medium">погашение</th>
                <th className="py-2.5 px-4 font-medium text-right">сумма</th>
                <th className="py-2.5 px-4 font-medium text-right">ставка</th>
                <th className="py-2.5 px-4 font-medium text-right">текущий долг</th>
                <th className="py-2.5 px-4 font-medium">статус</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {data!.items.map((r) => {
                const meta = STATUS_META[r.status] || { label: r.status, cls: '' }
                return (
                  <tr key={r.id} className="hover:bg-bg-subtle/40">
                    <td className="py-2.5 px-4 text-fg">{r.product_type_label}</td>
                    <td className="py-2.5 px-4 text-fg-muted">{r.cabinet_name}</td>
                    <td className="py-2.5 px-4 text-fg-muted text-xs tabular-nums">
                      {new Date(r.issued_at).toLocaleDateString('ru-RU')}
                    </td>
                    <td className="py-2.5 px-4 text-fg-muted text-xs tabular-nums">{r.due_date || '—'}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums">{formatCurrency(r.principal)}</td>
                    <td className="py-2.5 px-4 text-right tabular-nums text-fg-muted">
                      {r.interest_rate != null ? `${r.interest_rate}%` : '—'}
                    </td>
                    <td className={cn('py-2.5 px-4 text-right tabular-nums font-semibold',
                      r.current_debt > 0 ? 'text-rose-700' : 'text-fg-muted')}>
                      {formatCurrency(r.current_debt)}
                    </td>
                    <td className="py-2.5 px-4">
                      <span className={cn('text-xs font-medium px-1.5 py-0.5 rounded', meta.cls)}>{meta.label}</span>
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
