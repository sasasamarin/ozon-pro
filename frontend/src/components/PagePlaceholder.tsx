import type { LucideIcon } from 'lucide-react'
import { Sparkles } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { HelpHint } from '@/components/ui/HelpHint'

interface PagePlaceholderProps {
  icon: LucideIcon
  title: string
  description: string
  plannedFeatures: string[]
  badge?: string
}

export function PagePlaceholder({
  icon: Icon,
  title,
  description,
  plannedFeatures,
  badge,
}: PagePlaceholderProps) {
  return (
    <div className="relative max-w-3xl mx-auto pt-4">
      <div
        aria-hidden
        className="absolute -top-20 left-1/2 -translate-x-1/2 w-[420px] h-[420px] rounded-full bg-aurora-soft blur-3xl pointer-events-none -z-0"
      />

      <div className="relative flex flex-col items-center text-center">
        <div className="inline-flex items-center gap-2 rounded-full border border-border-subtle bg-bg-subtle/70 backdrop-blur-sm px-2.5 py-1 text-xs font-medium text-fg-muted mb-6">
          <Sparkles className="w-3 h-3" />
          {badge || 'Coming soon'}
        </div>

        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-white to-bg-subtle border border-border-subtle shadow-glass flex items-center justify-center mb-5">
          <Icon className="w-7 h-7 text-fg-muted" strokeWidth={1.5} />
        </div>

        <div className="flex items-center gap-2">
          <h1 className="text-3xl font-semibold text-fg tracking-tight text-balance">
            {title}
          </h1>
          <HelpHint
            text={
              description +
              (plannedFeatures.length
                ? '\n\nЧто будет:\n• ' + plannedFeatures.join('\n• ')
                : '')
            }
          />
        </div>
        <p className="text-base text-fg-muted mt-3 max-w-lg text-balance">{description}</p>

        <div className="mt-3 text-xs font-medium text-fg-subtle">
          Раздел в разработке
        </div>
      </div>

      {plannedFeatures.length > 0 && (
        <Card className="relative mt-10 p-6">
          <h2 className="text-sm font-semibold text-fg uppercase tracking-wider mb-4">
            Что будет в этом разделе
          </h2>
          <ul className="space-y-3">
            {plannedFeatures.map((feature, i) => (
              <li key={i} className="flex items-start gap-3">
                <span className="mt-2 w-1 h-1 rounded-full bg-fg-subtle shrink-0" />
                <span className="text-sm text-fg leading-relaxed">{feature}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
