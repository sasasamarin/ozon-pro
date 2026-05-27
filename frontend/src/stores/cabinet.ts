import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface CabinetState {
  selectedCabinetId: string | null
  setSelectedCabinetId: (id: string | null) => void
}

export const useCabinetStore = create<CabinetState>()(
  persist(
    (set) => ({
      selectedCabinetId: null,
      setSelectedCabinetId: (id) => set({ selectedCabinetId: id }),
    }),
    { name: 'flowoi_selected_cabinet' }
  )
)

export interface OzonAccountSummary {
  id: string
  name: string
  status: string
  is_active: boolean
  has_performance_api: boolean
  last_sync_at: string | null
}
