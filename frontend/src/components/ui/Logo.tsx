import { cn } from '@/lib/utils'

interface LogoProps {
  className?: string
}

export function Logo({ className }: LogoProps) {
  return (
    <img
      src="/logo-flowoi.png"
      alt="Flowoi"
      width={978}
      height={326}
      draggable={false}
      className={cn(
        'h-9 w-auto select-none mix-blend-multiply',
        className
      )}
    />
  )
}
