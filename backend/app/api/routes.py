"""
Главный API роутер.

Объединяет все endpoints (auth, products, orders, dashboard, etc.)
"""
from fastapi import APIRouter

from app.api.endpoints import (
    account_balance,
    auth,
    calculator,
    cashflow,
    categories,
    communications,
    costs,
    credit,
    dashboard,
    dashboard_v2,
    day_explanation,
    email_logs,
    expenses,
    funnel,
    funnel_v2,
    loans,
    reverse_funnel,
    product_stats,
    seasonality,
    ai_chat,
    ai_chat_v2,
    storage_warning,
    dashboard_builder,
    supplies,
    reconciliation,
    company_settings,
    product_economics,
    system_health,
    inventory_balance,
    metrics_matrix,
    ai_context,
    whatif,
    markers,
    orders,
    ozon_accounts,
    plan_purchase,
    plan_vs_fact,
    pnl,
    products,
    recommendations,
    returns,
    unit_economy,
    summary,
    supplier_orders,
    supply_params,
    team,
    transactions,
    warehouse_stocks,
)

api_router = APIRouter()

# Подключаем разделы
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(
    ozon_accounts.router, prefix="/ozon-accounts", tags=["ozon-accounts"]
)
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(
    dashboard_v2.router, prefix="/dashboard/v2", tags=["dashboard"]
)
api_router.include_router(products.router, prefix="/products", tags=["products"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(
    transactions.router, prefix="/finance/transactions", tags=["finance"]
)
api_router.include_router(
    funnel.router, prefix="/analytics/funnel", tags=["analytics"]
)
api_router.include_router(
    funnel_v2.router, prefix="/analytics/funnel/v2", tags=["analytics"]
)
api_router.include_router(
    seasonality.router, prefix="/seasonality", tags=["seasonality"]
)
api_router.include_router(
    ai_chat.router, prefix="/ai", tags=["ai"]
)
# AI Phase 1 — новые endpoints поверх ai_chat_sessions/messages (OpenAI function calling)
api_router.include_router(
    ai_chat_v2.router, prefix="/ai", tags=["ai"]
)
api_router.include_router(
    storage_warning.router, prefix="/storage-warning", tags=["analytics"]
)
api_router.include_router(
    day_explanation.router, prefix="/analytics/day-explanation", tags=["analytics"]
)
api_router.include_router(
    reconciliation.router, prefix="/reconciliation", tags=["reconciliation"]
)
api_router.include_router(
    company_settings.router, prefix="/company/settings", tags=["settings"]
)
api_router.include_router(
    product_economics.router, prefix="/products/economics", tags=["products"]
)
api_router.include_router(
    system_health.router, prefix="/system", tags=["system"]
)
api_router.include_router(
    inventory_balance.router, prefix="/inventory", tags=["inventory"]
)
api_router.include_router(
    metrics_matrix.router, prefix="/analytics/metrics-matrix", tags=["analytics"]
)
api_router.include_router(
    ai_context.router, prefix="/ai", tags=["ai"]
)
api_router.include_router(
    whatif.router, prefix="/whatif", tags=["whatif"]
)
api_router.include_router(
    calculator.router, prefix="/products/calculator", tags=["products"]
)
api_router.include_router(pnl.router, prefix="/finance/pnl", tags=["finance"])
api_router.include_router(
    unit_economy.router, prefix="/finance/unit-economy", tags=["finance"]
)
api_router.include_router(
    cashflow.router, prefix="/finance/cashflow", tags=["finance"]
)
api_router.include_router(returns.router, prefix="/returns", tags=["returns"])
api_router.include_router(
    warehouse_stocks.router, prefix="/warehouse-stocks", tags=["warehouses"]
)
api_router.include_router(summary.router, prefix="/analytics/summary", tags=["analytics"])
api_router.include_router(
    categories.router, prefix="/products/categories", tags=["products"]
)
api_router.include_router(costs.router, prefix="/costs", tags=["costs"])
api_router.include_router(
    supply_params.router, prefix="/supply-params", tags=["procurement"]
)
api_router.include_router(
    recommendations.router, prefix="/recommendations", tags=["recommendations"]
)
api_router.include_router(expenses.router, prefix="/finance/expenses", tags=["finance"])
api_router.include_router(
    supplier_orders.router, prefix="/procurement/orders", tags=["procurement"]
)
api_router.include_router(
    communications.router, prefix="/communications", tags=["communications"]
)
api_router.include_router(markers.router, prefix="/markers", tags=["markers"])
api_router.include_router(team.router, prefix="/team", tags=["team"])
api_router.include_router(
    plan_vs_fact.router, prefix="/analytics/plan-vs-fact", tags=["analytics"]
)
api_router.include_router(
    account_balance.router, prefix="/finance/account-balance", tags=["finance"]
)
api_router.include_router(
    plan_purchase.router, prefix="/analytics/plan-purchase", tags=["analytics"]
)
api_router.include_router(credit.router, prefix="/credit", tags=["credit"])
api_router.include_router(loans.router, prefix="/loans", tags=["loans"])
api_router.include_router(supplies.router, prefix="/supplies", tags=["supplies"])
api_router.include_router(product_stats.router, prefix="/products/stats", tags=["analytics"])
api_router.include_router(dashboard_builder.router, prefix="/dashboard/builder", tags=["dashboard"])
api_router.include_router(
    reverse_funnel.router, prefix="/analytics/reverse-funnel", tags=["analytics"],
)
api_router.include_router(email_logs.router, prefix="/email", tags=["email"])
