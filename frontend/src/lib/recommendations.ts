import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useCabinetStore } from '@/stores/cabinet'

export interface BuyoutMetric {
  rate: number
  confidence: 'high' | 'medium' | 'low'
  sample_size: number
  delivered: number
  returned: number
  arrived_total: number
  basis: string
}

export interface VelocityMetric {
  raw_avg_daily: number
  multiplier: number
  adjusted_daily: number
  confidence: 'high' | 'medium' | 'low'
  days_in_stock: number
  days_out_of_stock: number
  window_days: number
  total_units_sold: number
  basis: string
}

export interface ProcurementMetric {
  need_reorder: boolean
  /** null/Infinity = нет продаж в окне, days_left не определён. */
  days_left: number | null
  raw_need: number
  recommended_qty: number
  order_by: string | null
  projected_stockout: string | null
  confidence: 'high' | 'medium' | 'low'
  basis: string
  warnings: string[]
  signal: 'stockout' | 'reorder_now' | 'ok'
  lead_time_days: number
  safety_stock_days: number
  moq: number
  supply_params_set: boolean
}

export interface ROIMetric {
  roi_pct: number
  period_days: number
  profit_rub: number
  capital_rub: number
  confidence: 'high' | 'medium' | 'low'
  basis: string
}

export interface WorstCluster {
  cluster: string
  free_to_sell: number
  velocity_per_day: number
  days_left: number | null
  signal: 'stockout' | 'reorder_now' | 'ok'
}

export interface ProductRecommendation {
  product_id: string
  product_name: string
  offer_id: string
  ozon_sku: number
  current_price: number | null         // Ozon `price` (зачёркнутая 33000), ТОЛЬКО UI
  marketing_price?: number | null      // Ozon `marketing_seller_price` (рабочая)
  selling_price?: number | null        // canonical: marketing_price ?? current_price
  sales_percent_fbo?: number | null    // реальная %-комиссия Ozon
  cost_price: number | null
  is_archived?: boolean
  image_url: string | null
  current_stock: number
  in_transit_to_customer: number
  buyout: BuyoutMetric
  velocity: VelocityMetric
  procurement: ProcurementMetric | null
  roi_30d: ROIMetric | null
  abc_class: string | null
  abc_confidence: 'high' | 'medium' | 'low' | null
  missing_data: string[]
  worst_cluster: WorstCluster | null
}

export function useRecommendations() {
  const { selectedCabinetIds } = useCabinetStore()
  return useQuery<ProductRecommendation[]>({
    queryKey: ['recommendations', 'products', selectedCabinetIds],
    queryFn: async () => {
      const params = new URLSearchParams()
      selectedCabinetIds.forEach((id) => params.append('cabinet_ids', id))
      const qs = params.toString() ? `?${params.toString()}` : ''
      const res = await api.get(`/recommendations/products${qs}`, { timeout: 60000 })
      return res.data
    },
    staleTime: 60_000,
  })
}
