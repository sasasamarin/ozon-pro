import type { AxiosError } from 'axios'

interface FastAPIValidationItem {
  type?: string
  loc?: (string | number)[]
  msg?: string
  input?: unknown
}

export function getErrorMessage(err: unknown): string {
  const ax = err as AxiosError<{ detail?: string | FastAPIValidationItem[] }>
  const detail = ax?.response?.data?.detail

  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => (item && typeof item === 'object' ? item.msg : String(item)))
      .filter((s): s is string => Boolean(s))
    if (parts.length) return parts.join('; ')
  }

  if (ax?.message) return ax.message
  return 'Что-то пошло не так'
}
