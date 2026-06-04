/**
 * Pending AI context — для кнопки «Спросить у AI» с любого экрана.
 *
 * Flow:
 *   1. Юзер кликает <AskAIButton context={...}/> на странице/таблице/графике.
 *   2. Кнопка кладёт context в этот store + navigate('/ai/chat').
 *   3. AIChat на mount читает context, кладёт в attachments, очищает store.
 *
 * Это §5 FLOWOI_AI_TZ — «прикрепление графиков»: передаём СТРУКТУРНЫЙ
 * контекст (metrics + period + product_id + cabinet_id), не картинку.
 * AI получает точные данные через свои tools, не угадывает по скриншоту.
 */
import { create } from 'zustand'

export interface ChartContext {
  type: 'chart' | 'table' | 'screen'
  // Что показывает виджет: какие метрики (revenue, orders, ...)
  metrics: string[]
  // Период данных
  period?: { from: string; to: string }
  // Доп. филтры
  product_id?: string
  cabinet_id?: string
  // Человекочитаемое описание для AI («Воронка Жирафа за май»)
  source_page: string
  source_label?: string
  // Опционально: предзаполненный вопрос
  prefilled_question?: string
}

interface AIContextState {
  pending: ChartContext | null
  setPending: (ctx: ChartContext) => void
  consume: () => ChartContext | null
}

export const useAIContextStore = create<AIContextState>((set, get) => ({
  pending: null,
  setPending: (ctx) => set({ pending: ctx }),
  consume: () => {
    const ctx = get().pending
    set({ pending: null })
    return ctx
  },
}))
