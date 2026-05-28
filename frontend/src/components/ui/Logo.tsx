import { cn } from '@/lib/utils'

interface LogoProps {
  className?: string
}

export function Logo({ className }: LogoProps) {
  return (
    <img
      src="/logo-flowoi.png"
      alt="Flowoi"
      draggable={false}
      className={cn(
        // h-9 default по высоте, ширина auto от пропорций PNG,
        // self-start чтобы не растягивался по ширине родительского flex-col,
        // object-contain на случай если родитель навяжет фиксированные размеры,
        // mix-blend-multiply на белых поверхностях (sidebar/login bg-bg=white).
        'h-9 w-auto self-start object-contain select-none mix-blend-multiply',
        className
      )}
    />
  )
}
