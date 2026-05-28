import { cn } from '@/lib/utils'

interface LogoProps {
  className?: string
}

export function Logo({ className }: LogoProps) {
  return (
    <img
      src="/logo-flowoi.png"
      alt="Flowoi"
      width={1774}
      height={887}
      draggable={false}
      className={cn(
        'h-7 w-auto select-none mix-blend-multiply',
        className
      )}
    />
  )
}
