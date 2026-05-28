import { HelpCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

interface HelpHintProps {
  text: string
  /** Где появляется поповер относительно иконки. */
  placement?: 'right' | 'bottom' | 'left'
  className?: string
}

/**
 * Иконка «?» с подсказкой по hover/focus.
 *
 * Чистый CSS (group-hover + focus-within), без библиотек.
 * Ставим рядом с заголовком раздела, чтобы новый юзер мог быстро понять
 * назначение страницы и логику.
 */
export function HelpHint({ text, placement = 'bottom', className }: HelpHintProps) {
  return (
    <span className={cn('relative inline-flex group', className)}>
      <button
        type="button"
        aria-label="Подсказка к разделу"
        className="text-fg-subtle hover:text-fg-muted focus:text-fg-muted transition-colors focus:outline-none"
      >
        <HelpCircle className="w-4 h-4" strokeWidth={1.75} />
      </button>
      <span
        role="tooltip"
        className={cn(
          'pointer-events-none invisible opacity-0',
          'group-hover:visible group-hover:opacity-100',
          'group-focus-within:visible group-focus-within:opacity-100',
          'transition-opacity duration-150',
          'absolute z-50 w-80 max-w-[calc(100vw-2rem)]',
          'bg-fg text-bg text-[11px] leading-relaxed font-normal',
          'rounded-md px-3 py-2.5 shadow-elev',
          placement === 'bottom' && 'top-full left-1/2 -translate-x-1/2 mt-2',
          placement === 'right' && 'left-full top-1/2 -translate-y-1/2 ml-2',
          placement === 'left' && 'right-full top-1/2 -translate-y-1/2 mr-2',
        )}
      >
        {text}
      </span>
    </span>
  )
}
