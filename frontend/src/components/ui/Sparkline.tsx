import { useId } from 'react'
import { cn } from '@/lib/utils'

interface SparklineProps {
  points: number[]
  className?: string
  strokeWidth?: number
}

export function Sparkline({ points, className, strokeWidth = 1.5 }: SparklineProps) {
  const id = useId()
  const w = 120
  const h = 36
  if (points.length < 2) return null

  const min = Math.min(...points)
  const max = Math.max(...points)
  const range = max - min || 1
  const norm = points.map((p) => (p - min) / range)

  const path = norm
    .map((p, i) => {
      const x = (i / (norm.length - 1)) * w
      const y = h - p * (h - 2) - 1
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
    })
    .join(' ')
  const area = `${path} L ${w} ${h} L 0 ${h} Z`

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={cn('w-full h-9', className)} preserveAspectRatio="none">
      <defs>
        <linearGradient id={`spark-${id}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.22" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#spark-${id})`} />
      <path
        d={path}
        fill="none"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
