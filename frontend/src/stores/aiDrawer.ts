/**
 * AI Drawer state — slide-out панель чата справа на любой странице.
 *
 * Открывается с контекстом графика/таблицы. UI остаётся видим (не navigate).
 * Юзер видит график СЛЕВА, AI-разговор СПРАВА — обсуждает то же что видит.
 */
import { create } from 'zustand'
import type { ChartContext } from './aiContext'

interface DrawerState {
  isOpen: boolean
  context: ChartContext | null
  prefilledQuestion: string | null
  open: (ctx: ChartContext, question?: string) => void
  close: () => void
  toggle: () => void
}

export const useAIDrawerStore = create<DrawerState>((set, get) => ({
  isOpen: false,
  context: null,
  prefilledQuestion: null,
  open: (ctx, question) => set({
    isOpen: true,
    context: ctx,
    prefilledQuestion: question || ctx.prefilled_question || null,
  }),
  close: () => set({ isOpen: false }),
  toggle: () => set({ isOpen: !get().isOpen }),
}))
