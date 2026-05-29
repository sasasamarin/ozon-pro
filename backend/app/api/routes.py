"""
Главный API роутер.

Объединяет все endpoints (auth, products, orders, dashboard, etc.)
"""
from fastapi import APIRouter

from app.api.endpoints import (
    auth,
    costs,
    dashboard,
    funnel,
    orders,
    ozon_accounts,
    pnl,
    products,
    recommendations,
    transactions,
)

api_router = APIRouter()

# Подключаем разделы
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(
    ozon_accounts.router, prefix="/ozon-accounts", tags=["ozon-accounts"]
)
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(products.router, prefix="/products", tags=["products"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(
    transactions.router, prefix="/finance/transactions", tags=["finance"]
)
api_router.include_router(
    funnel.router, prefix="/analytics/funnel", tags=["analytics"]
)
api_router.include_router(pnl.router, prefix="/finance/pnl", tags=["finance"])
api_router.include_router(costs.router, prefix="/costs", tags=["costs"])
api_router.include_router(
    recommendations.router, prefix="/recommendations", tags=["recommendations"]
)
