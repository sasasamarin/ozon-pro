/**
 * Глобальный multi-tag фильтр для всех разделов.
 *
 * Пустой массив = «Все теги».
 * Иначе — товар должен иметь ХОТЯ БЫ ОДИН из выбранных тегов (OR-логика).
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface TagFilterState {
  selectedTags: string[]
  toggleTag: (tag: string) => void
  clear: () => void
  setTags: (tags: string[]) => void
}

export const useTagFilter = create<TagFilterState>()(
  persist(
    (set) => ({
      selectedTags: [],
      toggleTag: (tag) =>
        set((s) => ({
          selectedTags: s.selectedTags.includes(tag)
            ? s.selectedTags.filter((t) => t !== tag)
            : [...s.selectedTags, tag],
        })),
      clear: () => set({ selectedTags: [] }),
      setTags: (tags) => set({ selectedTags: tags }),
    }),
    { name: 'flowoi_selected_tags' }
  )
)
