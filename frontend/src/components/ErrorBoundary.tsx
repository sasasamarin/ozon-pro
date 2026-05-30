/**
 * ErrorBoundary — ловит React-исключения и показывает понятную ошибку
 * вместо белого экрана. Юзер: «белый экран = юзер думает что всё сломалось».
 */
import { Component, ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
  /** Зона действия для подписи "Ошибка в [name]". */
  name?: string
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // оставляем след в консоли для debugger'а, но рендер не падает
    console.error(`[ErrorBoundary${this.props.name ? `:${this.props.name}` : ''}]`, error, info)
  }

  render() {
    if (!this.state.hasError) return this.props.children
    if (this.props.fallback) return this.props.fallback

    const msg = this.state.error?.message || 'Неизвестная ошибка'
    return (
      <div className="rounded-lg border border-rose-300 bg-rose-50/60 p-5 text-sm text-rose-900">
        <div className="flex items-center gap-2 font-semibold mb-2">
          <AlertTriangle className="w-4 h-4" />
          Ошибка в блоке{this.props.name ? `: ${this.props.name}` : ''}
        </div>
        <p className="text-xs mb-3">{msg}</p>
        <button
          onClick={() => this.setState({ hasError: false, error: null })}
          className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-rose-300 hover:bg-rose-100"
        >
          <RefreshCw className="w-3 h-3" /> Перезапустить блок
        </button>
        <p className="text-[10px] text-rose-700 mt-3">
          Остальная страница продолжает работать. Если повторяется — сообщи /support.
        </p>
      </div>
    )
  }
}
