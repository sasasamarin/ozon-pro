/**
 * Глобальный single-category фильтр для всех разделов.
 *
 * NULL = «Все категории» (агрегат).
 * Любой ozon_id = эта категория + все её потомки (для родительских узлов).
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface CategoryFilterState {
  selectedCategoryId: number | null
  selectedCategoryName: string | null   // для отображения в Topbar
  selectedCategoryPath: string | null   // полный путь от корня для tooltip
  setSelectedCategory: (id: number | null, name: string | null, path: string | null) => void
  clear: () => void
}

export const useCategoryFilter = create<CategoryFilterState>()(
  persist(
    (set) => ({
      selectedCategoryId: null,
      selectedCategoryName: null,
      selectedCategoryPath: null,
      setSelectedCategory: (id, name, path) =>
        set({ selectedCategoryId: id, selectedCategoryName: name, selectedCategoryPath: path }),
      clear: () => set({ selectedCategoryId: null, selectedCategoryName: null, selectedCategoryPath: null }),
    }),
    { name: 'flowoi_selected_category' }
  )
)
