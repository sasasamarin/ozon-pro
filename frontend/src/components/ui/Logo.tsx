import { cn } from '@/lib/utils'

interface LogoProps {
  className?: string
  showText?: boolean
}

export function Logo({ className, showText = true }: LogoProps) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div className="w-7 h-7 rounded-md bg-accent flex items-center justify-center">
        <svg viewBox="0 0 16 16" className="w-4 h-4 text-white" fill="none">
          <path d="M2 4 L8 1 L14 4 L14 12 L8 15 L2 12 Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
          <path d="M8 1 L8 15" stroke="currentColor" strokeWidth="1.5" />
          <path d="M2 4 L8 7 L14 4" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
        </svg>
      </div>
      {showText && (
        <span className="font-semibold text-fg tracking-tight">Ozon Pro</span>
      )}
    </div>
  )
}
