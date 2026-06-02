/**
 * Helper: собрать URLSearchParams для эндпоинта поверх date-range.
 * Если есть dateFrom/dateTo — отправляет ТОЧНЫЕ даты, иначе days.
 *
 * Все backend endpoints должны принимать оба варианта:
 *   ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD   (приоритет)
 *   ?days=N                                     (fallback)
 */
export function dateParams(
  days: number,
  dateFrom: string | null,
  dateTo: string | null,
): URLSearchParams {
  const p = new URLSearchParams()
  if (dateFrom && dateTo) {
    p.set('date_from', dateFrom)
    p.set('date_to', dateTo)
  } else {
    p.set('days', String(days))
  }
  return p
}

/** Включить параметры в существующий URLSearchParams (мутирует) */
export function addDateParams(
  p: URLSearchParams,
  days: number,
  dateFrom: string | null,
  dateTo: string | null,
): URLSearchParams {
  if (dateFrom && dateTo) {
    p.set('date_from', dateFrom)
    p.set('date_to', dateTo)
  } else {
    p.set('days', String(days))
  }
  return p
}
