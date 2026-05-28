import type { AxiosError } from 'axios'

interface FastAPIValidationItem {
  type?: string
  loc?: (string | number)[]
  msg?: string
  input?: unknown
}

/**
 * Извлекает читаемое сообщение из чего угодно: строки, массива FastAPI
 * validation items, axios-error, объекта с msg/message/detail. Гарантирует
 * что результат — string, безопасный для рендера в JSX (никаких React #31).
 */
export function getErrorMessage(value: unknown): string {
  if (value == null) return ''

  // Plain string — уже готово
  if (typeof value === 'string') return value

  // FastAPI validation array (как пришёл в JSX напрямую)
  if (Array.isArray(value)) {
    const parts = value
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'msg' in item) return String((item as FastAPIValidationItem).msg ?? '')
        return ''
      })
      .filter(Boolean)
    if (parts.length) return parts.join('; ')
  }

  // Объект-ошибка: проверяем axios → detail → msg → message → fallback
  if (typeof value === 'object') {
    const ax = value as AxiosError<{ detail?: string | FastAPIValidationItem[] }>
    const detail = ax?.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      const parts = detail
        .map((item) => (item && typeof item === 'object' ? item.msg : String(item)))
        .filter((s): s is string => Boolean(s))
      if (parts.length) return parts.join('; ')
    }

    // Не axios — может, есть msg или message
    const v = value as { msg?: unknown; message?: unknown }
    if (typeof v.msg === 'string') return v.msg
    if (typeof v.message === 'string') return v.message
  }

  return 'Что-то пошло не так'
}
