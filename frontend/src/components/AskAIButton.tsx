/**
 * Универсальная кнопка «Спросить у AI» для любой страницы/виджета.
 *
 * Использование:
 *   <AskAIButton
 *     context={{
 *       type: 'table',
 *       source_page: 'storage-warning',
 *       source_label: 'Хранение по SKU',
 *       metrics: ['storage_30d_rub', 'days_of_inventory', 'storage_share_pct'],
 *       period: { from: '2026-05-01', to: '2026-06-01' },
 *       cabinet_id: cabinetId,
 *     }}
 *     question="Какие SKU забить в распродажу?"
 *   />
 *
 * Кликает → передаёт контекст в store + navigate /ai/chat.
 * AIChat на mount подхватывает и кладёт в attachments + (если есть)
 * заполняет input prefilled_question.
 */
import { Sparkles } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAIContextStore, type ChartContext } from '@/stores/aiContext'
import { cn } from '@/lib/utils'

interface AskAIButtonProps {
  context: ChartContext
  question?: string         // shortcut для prefilled_question
  size?: 'sm' | 'md'
  variant?: 'ghost' | 'solid'
  label?: string
  className?: string
}

export function AskAIButton({
  context,
  question,
  size = 'sm',
  variant = 'ghost',
  label,
  className,
}: AskAIButtonProps) {
  const navigate = useNavigate()
  const setPending = useAIContextStore((s) => s.setPending)

  const handleClick = () => {
    setPending({
      ...context,
      prefilled_question: question || context.prefilled_question,
    })
    navigate('/ai/chat')
  }

  const styles = cn(
    'inline-flex items-center gap-1.5 rounded transition-colors',
    size === 'sm' ? 'px-2 py-1 text-xs' : 'px-3 py-1.5 text-sm',
    variant === 'ghost'
      ? 'text-violet-600 hover:bg-violet-50 border border-transparent hover:border-violet-200'
      : 'bg-violet-600 text-white hover:bg-violet-700',
    className,
  )

  return (
    <button onClick={handleClick} className={styles} type="button">
      <Sparkles className={size === 'sm' ? 'w-3 h-3' : 'w-4 h-4'} />
      <span>{label ?? 'Спросить AI'}</span>
    </button>
  )
}
