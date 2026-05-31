/**
 * Баннер «Выбран товар X» на страницах где endpoint не поддерживает product_id.
 * Предлагает перейти в карточку товара / экономику для детального разреза.
 */
import { Link } from 'react-router-dom'
import { Package, ArrowRight, X } from 'lucide-react'
import { useProductFilter } from '@/stores/product_filter'

interface Props {
  /** На этой странице фильтр товара РАБОТАЕТ (не показывать переадресацию) */
  supported?: boolean
}

export function SelectedProductBanner({ supported = false }: Props) {
  const { selectedProductId, selectedProductName, clear } = useProductFilter()
  if (!selectedProductId) return null

  if (supported) {
    // Поддерживается на странице — лёгкий info-баннер
    return (
      <div className="rounded-md border border-blue-200 bg-blue-50/50 px-3 py-2 text-xs text-blue-900 flex items-center gap-2">
        <Package className="w-3.5 h-3.5 text-blue-700 shrink-0" />
        <span>Фильтр товара: <strong>{selectedProductName}</strong></span>
        <button onClick={clear} className="ml-auto text-blue-700 hover:underline inline-flex items-center gap-1">
          <X className="w-3 h-3" /> сбросить
        </button>
      </div>
    )
  }

  // НЕ поддерживается — предложение перейти в карточку товара
  return (
    <div className="rounded-md border border-amber-200 bg-amber-50/60 px-3 py-2.5 text-xs text-amber-900 flex items-center gap-2 flex-wrap">
      <Package className="w-3.5 h-3.5 text-amber-700 shrink-0" />
      <span>
        Этот раздел показывает АГРЕГАТ по всем товарам. Глобальный фильтр товара
        («{selectedProductName}») здесь не применяется.
      </span>
      <Link
        to={`/products/${selectedProductId}`}
        className="ml-auto inline-flex items-center gap-1 px-2 py-1 rounded bg-amber-100 text-amber-900 hover:bg-amber-200 font-medium"
      >
        Открыть карточку «{(selectedProductName || '').slice(0, 30)}…» <ArrowRight className="w-3 h-3" />
      </Link>
      <button onClick={clear} className="text-amber-700 hover:underline">
        × сбросить
      </button>
    </div>
  )
}
