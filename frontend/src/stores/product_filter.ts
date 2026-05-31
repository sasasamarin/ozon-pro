/**
 * Глобальный single-product фильтр для всех разделов
 * (Dashboard, P&L, Cashflow, Inventory Balance, Воронка, Экономика, AI и т.д.).
 *
 * Пустая строка / null = «Все товары» (агрегат).
 * Любой product_id = ровно этот товар.
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface ProductFilterState {
  selectedProductId: string | null
  selectedProductName: string | null  // для отображения в Topbar
  setSelectedProduct: (id: string | null, name: string | null) => void
  clear: () => void
}

export const useProductFilter = create<ProductFilterState>()(
  persist(
    (set) => ({
      selectedProductId: null,
      selectedProductName: null,
      setSelectedProduct: (id, name) =>
        set({ selectedProductId: id, selectedProductName: name }),
      clear: () => set({ selectedProductId: null, selectedProductName: null }),
    }),
    { name: 'flowoi_selected_product' }
  )
)
