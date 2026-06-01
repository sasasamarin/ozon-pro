/**
 * Tooltip-индикатор источника цифры. Принцип «честность»: юзер видит откуда
 * каждое число (api/xlsx/manual/estimated/missing).
 *
 * Использование: рядом с числом в таблице ставится <SourceBadge source="xlsx" />
 * — маленькая иконка с tooltip-объяснением.
 */
import { cn } from '@/lib/utils'

type Source = 'api' | 'xlsx' | 'estimated' | 'manual' | 'missing'

const META: Record<Source, { color: string; bg: string; symbol: string; title: string; tip: string }> = {
  api: {
    symbol: '●', color: 'text-emerald-700', bg: 'bg-emerald-100',
    title: 'API live',
    tip: 'Прямые данные из Ozon API — синкаются ежечасно. Точная цифра.',
  },
  xlsx: {
    symbol: '◆', color: 'text-blue-700', bg: 'bg-blue-100',
    title: 'XLSX Ozon',
    tip: 'Точное число из загруженного отчёта «Экономика магазина» — зеркало Ozon.',
  },
  manual: {
    symbol: '✎', color: 'text-violet-700', bg: 'bg-violet-100',
    title: 'Ваш ввод',
    tip: 'Введено вручную (себестоимость). Если не заполнено — прибыль завышена.',
  },
  estimated: {
    symbol: '~', color: 'text-amber-700', bg: 'bg-amber-100',
    title: 'Оценка',
    tip: 'Расчётная эвристика — API per-SKU этого не отдаёт. Загрузите XLSX «Экономика магазина» для точных чисел.',
  },
  missing: {
    symbol: '?', color: 'text-rose-700', bg: 'bg-rose-100',
    title: 'Нет данных',
    tip: 'Данных нет ни в API, ни в XLSX, ни в ручном вводе. Заполни вручную или загрузи отчёт.',
  },
}

export function SourceBadge({ source, className }: { source: string | undefined; className?: string }) {
  const meta = META[source as Source]
  if (!meta) return null
  return (
    <span
      title={`${meta.title}: ${meta.tip}`}
      className={cn(
        'inline-flex items-center justify-center w-4 h-4 rounded text-[10px] font-bold leading-none cursor-help',
        meta.bg, meta.color, className,
      )}
    >
      {meta.symbol}
    </span>
  )
}

export function SourceLegend() {
  const order: Source[] = ['api', 'xlsx', 'manual', 'estimated', 'missing']
  return (
    <div className="flex items-center gap-3 text-[11px] text-fg-muted flex-wrap">
      <span className="font-medium text-fg-subtle uppercase tracking-wider">Источники:</span>
      {order.map((s) => {
        const m = META[s]
        return (
          <span key={s} className="inline-flex items-center gap-1" title={m.tip}>
            <span className={cn('inline-flex items-center justify-center w-4 h-4 rounded text-[10px] font-bold leading-none', m.bg, m.color)}>
              {m.symbol}
            </span>
            <span>{m.title}</span>
          </span>
        )
      })}
    </div>
  )
}
