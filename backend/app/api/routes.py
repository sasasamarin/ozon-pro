"""
Главный API роутер.

Объединяет все endpoints (auth, products, orders, dashboard, etc.)
"""
from fastapi import APIRouter

from app.api.endpoints import auth, dashboard, ozon_accounts

api_router = APIRouter()

# Подключаем разделы
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(
    ozon_accounts.router, prefix="/ozon-accounts", tags=["ozon-accounts"]
)
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
