import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/**
 * Состояние выбора кабинетов для multi-select переключателя в Topbar.
 *
 * Семантика: пустой массив = «Все кабинеты» (нет фильтра).
 * Любой не-пустой массив = ровно эти ID.
 *
 * Click-rules:
 * - «Все кабинеты» → set([])
 * - Если сейчас «Все» ([]) и кликнули по индивидуальному кабинету → set([id])
 *   (свитчимся в «только этот», не «добавляем к Всем»).
 * - Если кабинет уже в массиве → remove из массива
 *   (когда массив пустеет, авто-возвращаемся в «Все»).
 * - Если кабинет НЕ в массиве и массив не пустой → add.
 */
interface CabinetState {
  selectedCabinetIds: string[]
  setSelectedCabinetIds: (ids: string[]) => void
  toggleCabinetId: (id: string) => void
  selectAll: () => void
}

export const useCabinetStore = create<CabinetState>()(
  persist(
    (set, get) => ({
      selectedCabinetIds: [],
      setSelectedCabinetIds: (ids) => set({ selectedCabinetIds: ids }),
      selectAll: () => set({ selectedCabinetIds: [] }),
      toggleCabinetId: (id) => {
        const cur = get().selectedCabinetIds
        if (cur.length === 0) {
          // «Все» был выбран → switch to «только этот»
          set({ selectedCabinetIds: [id] })
          return
        }
        if (cur.includes(id)) {
          set({ selectedCabinetIds: cur.filter((x) => x !== id) })
        } else {
          set({ selectedCabinetIds: [...cur, id] })
        }
      },
    }),
    { name: 'flowoi_selected_cabinets' }
  )
)

export interface OzonAccountSummary {
  id: string
  name: string
  description: string | null
  status: string
  is_active: boolean
  premium_tier: 'free' | 'premium' | 'premium_plus' | 'premium_pro'
  has_performance_api: boolean
  last_sync_at: string | null
  last_sync_error: string | null
}
