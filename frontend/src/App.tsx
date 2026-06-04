import { Routes, Route, Navigate } from 'react-router-dom'
import { Login } from '@/pages/Login'
import { AcceptInvite } from '@/pages/AcceptInvite'
import { Seasonality } from '@/pages/Seasonality'
import { StorageWarning } from '@/pages/StorageWarning'
import { Competitor } from '@/pages/Competitor'
import { CompetitorPrices } from '@/pages/CompetitorPrices'
import { Margin } from '@/pages/Margin'
import { Taxes } from '@/pages/Taxes'
import { Register } from '@/pages/Register'
import { Dashboard } from '@/pages/Dashboard'
import { DashboardBuilder } from '@/pages/DashboardBuilder'
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
import { Expenses } from '@/pages/Expenses'
import { SupplierOrders } from '@/pages/SupplierOrders'
import { Reviews } from '@/pages/Reviews'
import { Questions } from '@/pages/Questions'
import { Markers } from '@/pages/Markers'
import { Team } from '@/pages/Team'
import { AIChat } from '@/pages/AIChat'
import { ReverseFunnel } from '@/pages/ReverseFunnel'
import { PlanVsFact } from '@/pages/PlanVsFact'
import { PlanPurchase } from '@/pages/PlanPurchase'
import { AccountBalance } from '@/pages/AccountBalance'
import { Credit } from '@/pages/Credit'
import { Loans } from '@/pages/Loans'
import { LoansSchedule } from '@/pages/LoansSchedule'
import { LoansCashflowImpact } from '@/pages/LoansCashflowImpact'
import { LoansRefinance } from '@/pages/LoansRefinance'
import { Suppliers } from '@/pages/Suppliers'
import { ProcurementCalendar } from '@/pages/ProcurementCalendar'
import { ProcurementQuality } from '@/pages/ProcurementQuality'
import { AlertsActive } from '@/pages/AlertsActive'
import { AlertsSettings } from '@/pages/AlertsSettings'
import { AlertsHistory } from '@/pages/AlertsHistory'
import { AlertsChannels } from '@/pages/AlertsChannels'
import { Telegram } from '@/pages/Telegram'
import { Integrations } from '@/pages/Integrations'
import { Supplies } from '@/pages/Supplies'
import { SupplyDetailPage } from '@/pages/SupplyDetail'
import { ProductStats } from '@/pages/ProductStats'
import { Email } from '@/pages/Email'
import { Settings } from '@/pages/Settings'
import { SettingsReconciliation } from '@/pages/SettingsReconciliation'
import { ProductEconomics } from '@/pages/ProductEconomics'
import { UnitEconomyImport } from '@/pages/UnitEconomyImport'
import { InventoryBalance } from '@/pages/InventoryBalance'
import { MetricsMatrix } from '@/pages/MetricsMatrix'
import { MetricsBuilder } from '@/pages/MetricsBuilder'
import { WhatIf } from '@/pages/WhatIf'
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
      <Route path="/accept-invite" element={<AcceptInvite />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardBuilder />} />
        <Route path="/dashboard/legacy" element={<Dashboard />} />
        <Route path="/cabinets" element={<Cabinets />} />
        <Route path="/cabinets/new" element={<CabinetNew />} />
        <Route path="/cabinets/:id" element={<CabinetEdit />} />
        <Route path="/products" element={<Products />} />
        <Route path="/orders" element={<Orders />} />
        <Route path="/orders/fbo" element={<Orders />} />
        <Route path="/orders/fbs" element={<Orders />} />
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
        <Route path="/products/economics" element={<ProductEconomics />} />
        <Route path="/finance/balance" element={<InventoryBalance />} />
        <Route path="/finance/unit-economy/import" element={<UnitEconomyImport />} />
        <Route path="/analytics/metrics-matrix" element={<MetricsMatrix />} />
        <Route path="/analytics/builder" element={<MetricsBuilder />} />
        <Route path="/whatif" element={<WhatIf />} />
        <Route path="/finance/expenses" element={<Expenses />} />
        <Route path="/procurement/orders" element={<SupplierOrders />} />
        <Route path="/communications/reviews" element={<Reviews />} />
        <Route path="/communications/questions" element={<Questions />} />
        <Route path="/markers" element={<Markers />} />
        <Route path="/markers/list" element={<Markers />} />
        <Route path="/markers/timeline" element={<Markers />} />
        <Route path="/team" element={<Team />} />
        <Route path="/team/members" element={<Team />} />
        <Route path="/team/invitations" element={<Team />} />
        <Route path="/ai/chat" element={<AIChat />} />
        <Route path="/ai" element={<AIChat />} />
        <Route path="/analytics/reverse-funnel" element={<ReverseFunnel />} />
        <Route path="/analytics/seasonality" element={<Seasonality />} />
        <Route path="/analytics/storage-warning" element={<StorageWarning />} />
        <Route path="/analytics/competitor" element={<Competitor />} />
        <Route path="/products/competitors" element={<CompetitorPrices />} />
        <Route path="/finance/margin" element={<Margin />} />
        <Route path="/finance/taxes" element={<Taxes />} />
        <Route path="/analytics/plan-vs-fact" element={<PlanVsFact />} />
        <Route path="/analytics/plan-purchase" element={<PlanPurchase />} />
        <Route path="/finance/account-balance" element={<AccountBalance />} />
        <Route path="/credit" element={<Credit />} />
        <Route path="/credit/list" element={<Credit />} />
        <Route path="/loans" element={<Loans />} />
        <Route path="/credits" element={<Loans />} />
        <Route path="/credits/schedule" element={<LoansSchedule />} />
        <Route path="/credits/cashflow-impact" element={<LoansCashflowImpact />} />
        <Route path="/credits/refinance" element={<LoansRefinance />} />
        <Route path="/procurement/suppliers" element={<Suppliers />} />
        <Route path="/procurement/calendar" element={<ProcurementCalendar />} />
        <Route path="/procurement/quality" element={<ProcurementQuality />} />
        <Route path="/alerts" element={<AlertsActive />} />
        <Route path="/alerts/settings" element={<AlertsSettings />} />
        <Route path="/alerts/history" element={<AlertsHistory />} />
        <Route path="/alerts/channels" element={<AlertsChannels />} />
        <Route path="/telegram" element={<Telegram />} />
        <Route path="/integrations" element={<Integrations />} />
        <Route path="/procurement/supplies" element={<Supplies />} />
        <Route path="/procurement/supplies/:id" element={<SupplyDetailPage />} />
        <Route path="/products/stats" element={<ProductStats />} />
        <Route path="/email" element={<Email />} />
        <Route path="/email/templates" element={<Email />} />
        <Route path="/email/log" element={<Email />} />
        <Route path="/products/:id" element={<ProductDetail />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/settings/reconciliation" element={<SettingsReconciliation />} />

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
              item.path !== '/products/calculator' &&
              item.path !== '/products/economics' &&
              item.path !== '/finance/balance' &&
              item.path !== '/analytics/metrics-matrix' &&
              item.path !== '/analytics/builder' &&
              item.path !== '/whatif' &&
              item.path !== '/finance/expenses' &&
              item.path !== '/procurement/orders' &&
              item.path !== '/communications/reviews' &&
              item.path !== '/communications/questions' &&
              item.path !== '/markers/list' &&
              item.path !== '/markers/timeline' &&
              item.path !== '/team/members' &&
              item.path !== '/team/invitations' &&
              item.path !== '/ai/chat' &&
              item.path !== '/analytics/reverse-funnel' &&
              item.path !== '/analytics/seasonality' &&
              item.path !== '/analytics/storage-warning' &&
              item.path !== '/analytics/competitor' &&
              item.path !== '/products/competitors' &&
              item.path !== '/orders/fbo' &&
              item.path !== '/orders/fbs' &&
              item.path !== '/finance/margin' &&
              item.path !== '/finance/taxes' &&
              item.path !== '/analytics/plan-vs-fact' &&
              item.path !== '/finance/account-balance' &&
              item.path !== '/credit/list' &&
              item.path !== '/credits' &&
              item.path !== '/loans' &&
              item.path !== '/credits/schedule' &&
              item.path !== '/credits/cashflow-impact' &&
              item.path !== '/credits/refinance' &&
              item.path !== '/procurement/calendar' &&
              item.path !== '/procurement/quality' &&
              item.path !== '/procurement/suppliers' &&
              item.path !== '/procurement/supplies' &&
              item.path !== '/alerts' &&
              item.path !== '/alerts/settings' &&
              item.path !== '/alerts/history' &&
              item.path !== '/alerts/channels' &&
              item.path !== '/telegram' &&
              item.path !== '/integrations' &&
              item.path !== '/email/templates' &&
              item.path !== '/email/log',
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
