"""
Главный API роутер.

Объединяет все endpoints (auth, products, orders, dashboard, etc.)
"""
from fastapi import APIRouter

from app.api.endpoints import (
    account_balance,
    auth,
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
    reconciliation,
    markers,
    orders,
    ozon_accounts,
    plan_purchase,
    plan_vs_fact,
    pnl,
    products,
    recommendations,
    returns,
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
    day_explanation.router, prefix="/analytics/day-explanation", tags=["analytics"]
)
api_router.include_router(
    reconciliation.router, prefix="/reconciliation", tags=["reconciliation"]
)
api_router.include_router(pnl.router, prefix="/finance/pnl", tags=["finance"])
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
api_router.include_router(email_logs.router, prefix="/email", tags=["email"])
