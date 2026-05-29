import { Routes, Route, Navigate } from 'react-router-dom'
import { Login } from '@/pages/Login'
import { Register } from '@/pages/Register'
import { Dashboard } from '@/pages/Dashboard'
import { Cabinets } from '@/pages/Cabinets'
import { CabinetNew } from '@/pages/CabinetNew'
import { CabinetEdit } from '@/pages/CabinetEdit'
import { Products } from '@/pages/Products'
import { Orders } from '@/pages/Orders'
import { FinanceTransactions } from '@/pages/FinanceTransactions'
import { Stockouts } from '@/pages/Stockouts'
import { ProcurementForecast } from '@/pages/ProcurementForecast'
import { Funnel } from '@/pages/Funnel'
import { FinancePnL } from '@/pages/FinancePnL'
import { Costs } from '@/pages/Costs'
import { SupplyParams } from '@/pages/SupplyParams'
import { Cashflow } from '@/pages/Cashflow'
import { Returns } from '@/pages/Returns'
import { StockoutsByRegion } from '@/pages/StockoutsByRegion'
import { ProductDetail } from '@/pages/ProductDetail'
import { Summary } from '@/pages/Summary'
import { Categories } from '@/pages/Categories'
import { Calculator } from '@/pages/Calculator'
import { Heatmap } from '@/pages/Heatmap'
import { Settings } from '@/pages/Settings'
import { AppLayout } from '@/components/AppLayout'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { PagePlaceholder } from '@/components/PagePlaceholder'
import { getAllPlaceholderItems } from '@/lib/menu'

export default function App() {
  const placeholderItems = getAllPlaceholderItems()

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/cabinets" element={<Cabinets />} />
        <Route path="/cabinets/new" element={<CabinetNew />} />
        <Route path="/cabinets/:id" element={<CabinetEdit />} />
        <Route path="/products" element={<Products />} />
        <Route path="/orders" element={<Orders />} />
        <Route path="/finance/transactions" element={<FinanceTransactions />} />
        <Route path="/analytics/stockouts" element={<Stockouts />} />
        <Route path="/procurement/forecast" element={<ProcurementForecast />} />
        <Route path="/analytics/funnel" element={<Funnel />} />
        <Route path="/finance/p-and-l" element={<FinancePnL />} />
        <Route path="/finance/pnl" element={<FinancePnL />} />
        <Route path="/products/prices" element={<Costs />} />
        <Route path="/costs" element={<Costs />} />
        <Route path="/procurement/supply-params" element={<SupplyParams />} />
        <Route path="/supply-params" element={<SupplyParams />} />
        <Route path="/finance/cashflow" element={<Cashflow />} />
        <Route path="/orders/returns" element={<Returns />} />
        <Route path="/orders/cancellations" element={<Returns />} />
        <Route path="/returns" element={<Returns />} />
        <Route path="/analytics/stockouts-by-region" element={<StockoutsByRegion />} />
        <Route path="/analytics/summary" element={<Summary />} />
        <Route path="/analytics/heatmap" element={<Heatmap />} />
        <Route path="/products/categories" element={<Categories />} />
        <Route path="/products/calculator" element={<Calculator />} />
        <Route path="/products/:id" element={<ProductDetail />} />
        <Route path="/settings" element={<Settings />} />

        {placeholderItems
          .filter(
            (item) =>
              item.path !== '/products' &&
              item.path !== '/orders' &&
              item.path !== '/finance/transactions' &&
              item.path !== '/analytics/stockouts' &&
              item.path !== '/procurement/forecast' &&
              item.path !== '/analytics/funnel' &&
              item.path !== '/finance/p-and-l' &&
              item.path !== '/products/prices' &&
              item.path !== '/finance/cashflow' &&
              item.path !== '/orders/returns' &&
              item.path !== '/orders/cancellations' &&
              item.path !== '/analytics/summary' &&
              item.path !== '/analytics/heatmap' &&
              item.path !== '/products/categories' &&
              item.path !== '/products/calculator',
          )
          .map((item) => (
            <Route
              key={item.path}
              path={item.path}
              element={
                <PagePlaceholder
                  icon={item.icon}
                  title={item.label}
                  description={item.placeholder!.description}
                  plannedFeatures={item.placeholder!.plannedFeatures}
                />
              }
            />
          ))}
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
