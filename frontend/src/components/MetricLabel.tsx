/**
 * MetricLabel — лейбл метрики с info-иконкой и hover-tooltip.
 *
 * Использование:
 *   <MetricLabel metricKey="revenue" />        — рендерит "Выручка" + (i)
 *   <MetricLabel metricKey="revenue" override="Продажи (доставлено)" />
 *
 * Tooltip показывает: описание, формулу, источник (api/estimated/...),
 * когда смотреть, на что обратить внимание, и ссылку на детали.
 */
import { useState } from 'react'
import { Info, ExternalLink } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getMetricInfo, SOURCE_LABEL, type MetricInfo } from '@/lib/metric-info'
import { cn } from '@/lib/utils'


interface Props {
  metricKey: string
  override?: string           // если нужен кастомный label
  className?: string
  iconClassName?: string
  hideIcon?: boolean
}

export function MetricLabel({ metricKey, override, className, iconClassName, hideIcon }: Props) {
  const info = getMetricInfo(metricKey)
  const [open, setOpen] = useState(false)

  if (!info) {
    // Unknown metric — рендерим override или ключ
    return <span className={className}>{override || metricKey}</span>
  }

  return (
    <span className={cn('inline-flex items-center gap-1 group', className)}>
      <span>{override || info.label}</span>
      {!hideIcon && (
        <span
          className="relative inline-flex items-center justify-center cursor-help
                     w-6 h-6 -m-1.5 sm:w-4 sm:h-4 sm:m-0"
          onMouseEnter={() => setOpen(true)}
          onMouseLeave={() => setOpen(false)}
          onClick={(e) => { e.stopPropagation(); setOpen((o) => !o) }}
        >
          <Info className={cn('w-3 h-3 text-fg-subtle opacity-60 group-hover:opacity-100', iconClassName)} />
          {open && <MetricTooltipBox info={info} />}
        </span>
      )}
    </span>
  )
}


function MetricTooltipBox({ info }: { info: MetricInfo }) {
  const src = SOURCE_LABEL[info.source]
  return (
    <div className="absolute left-1/2 -translate-x-1/2 top-5 z-50 w-80 p-3
                    bg-surface border border-border rounded-lg shadow-elev
                    text-left normal-case tracking-normal animate-fade-in">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="text-sm font-semibold text-fg">{info.label}</div>
        <span className={cn('text-[9px] px-1.5 py-0.5 rounded uppercase tracking-wider', src.tone)}>
          {src.label}
        </span>
      </div>

      <div className="text-xs text-fg leading-relaxed">{info.description}</div>

      {info.formula && (
        <div className="mt-2 px-2 py-1.5 bg-bg-subtle rounded text-[11px] font-mono text-fg-muted leading-snug break-words">
          {info.formula}
        </div>
      )}

      {info.whenToCheck && (
        <div className="mt-2 text-[11px] text-fg-muted">
          <b className="text-fg">Когда смотреть: </b>{info.whenToCheck}
        </div>
      )}

      {info.cautions && info.cautions.length > 0 && (
        <ul className="mt-2 space-y-1 text-[11px] text-fg-muted list-disc pl-4">
          {info.cautions.map((c, i) => <li key={i}>{c}</li>)}
        </ul>
      )}

      {info.link && (
        <Link to={info.link}
              onClick={(e) => e.stopPropagation()}
              className="mt-2 inline-flex items-center gap-1 text-[11px] text-blue-600 hover:underline">
          Подробнее <ExternalLink className="w-3 h-3" />
        </Link>
      )}
    </div>
  )
}


/** Просто badge источника без лейбла. Для inline-использования около цифр. */
export function MetricSourceBadge({ source }: { source: keyof typeof SOURCE_LABEL }) {
  const s = SOURCE_LABEL[source]
  return (
    <span className={cn('text-[9px] px-1.5 py-0.5 rounded uppercase tracking-wider', s.tone)}>
      {s.label}
    </span>
  )
}
