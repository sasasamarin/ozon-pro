"""
AI Bridge — endpoints, к которым ходит внешний AI-сервис (ozon-pro-ai на Render).

Защищены SERVICE_TOKEN (Bearer header). Не путать с user-JWT — это
machine-to-machine.

Маппинг путей данными FLOWOI_AI_TZ §6 + клиент в ozon-pro-ai/tools/:
  data-tools:
    GET /api/v1/analytics/metrics
    GET /api/v1/finance/pnl
    GET /api/v1/analytics/funnel
    GET /api/v1/analytics/stock
    GET /api/v1/products/price
  model-tools:
    GET /api/v1/models/elasticity
    GET /api/v1/models/unit-economics
    GET /api/v1/models/demand-forecast
    GET /api/v1/models/price-optimizer
    GET /api/v1/models/keep-or-drop

Логика переиспользует services/ai/tools_v2.* — те же функции что использует
in-process orchestrator. AI не дублирует расчёты.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_service import get_service_user
from app.db.session import get_db
from app.models import User
from app.services.ai import tools_v2


router = APIRouter()


# ============================================================
# DATA-TOOLS
# ============================================================


@router.get("/analytics/metrics")
async def metrics(
    cabinet_id: str | None = Query(None),
    product_id: str | None = Query(None),
    period_from: str | None = Query(None),
    period_to: str | None = Query(None),
    metrics: list[str] | None = Query(None),
    user: User = Depends(get_service_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await tools_v2.get_metrics(
        db, user.company_id,
        cabinet_id=cabinet_id, product_id=product_id,
        period_from=period_from, period_to=period_to,
        metrics=metrics,
    )


@router.get("/finance/pnl")
async def pnl_view(
    cabinet_id: str | None = Query(None),
    period_from: str | None = Query(None),
    period_to: str | None = Query(None),
    model: str = Query("operational", description="operational | official"),
    user: User = Depends(get_service_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await tools_v2.get_pnl(
        db, user.company_id,
        cabinet_id=cabinet_id, period_from=period_from, period_to=period_to,
        model=model,
    )


@router.get("/analytics/funnel")
async def funnel_view(
    cabinet_id: str | None = Query(None),
    product_id: str | None = Query(None),
    period_from: str | None = Query(None),
    period_to: str | None = Query(None),
    user: User = Depends(get_service_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await tools_v2.get_funnel(
        db, user.company_id,
        cabinet_id=cabinet_id, product_id=product_id,
        period_from=period_from, period_to=period_to,
    )


@router.get("/analytics/stock")
async def stock_view(
    cabinet_id: str | None = Query(None),
    product_id: str | None = Query(None),
    user: User = Depends(get_service_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await tools_v2.get_stock(
        db, user.company_id,
        cabinet_id=cabinet_id, product_id=product_id,
    )


@router.get("/products/price")
async def price_view(
    product_id: str = Query(...),
    user: User = Depends(get_service_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await tools_v2.get_price(db, user.company_id, product_id=product_id)


# ============================================================
# MODEL-TOOLS
# ============================================================


@router.get("/models/elasticity")
async def elasticity_view(
    product_id: str = Query(...),
    user: User = Depends(get_service_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await tools_v2.elasticity(db, user.company_id, product_id=product_id)


@router.get("/models/unit-economics")
async def unit_economics_view(
    product_id: str = Query(...),
    price: float | None = Query(None),
    user: User = Depends(get_service_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await tools_v2.unit_economics(
        db, user.company_id, product_id=product_id, price=price,
    )


@router.get("/models/demand-forecast")
async def demand_forecast_view(
    product_id: str = Query(...),
    horizon_months: int = Query(3, ge=1, le=24),
    user: User = Depends(get_service_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await tools_v2.demand_forecast(
        db, user.company_id, product_id=product_id, horizon_months=horizon_months,
    )


@router.get("/models/price-optimizer")
async def price_optimizer_view(
    product_id: str = Query(...),
    search_range_pct: float = Query(20),
    user: User = Depends(get_service_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await tools_v2.price_optimizer(
        db, user.company_id, product_id=product_id,
        search_range_pct=search_range_pct,
    )


@router.get("/models/keep-or-drop")
async def keep_or_drop_view(
    product_id: str = Query(...),
    user: User = Depends(get_service_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await tools_v2.keep_or_drop(db, user.company_id, product_id=product_id)


# ============================================================
# HEALTH (для Render check + быстрого smoke)
# ============================================================


@router.get("/health")
async def health(user: User = Depends(get_service_user)) -> dict:
    """Проверка что service-token принят + company_id найден."""
    return {
        "ok": True,
        "service_user_id": str(user.id),
        "company_id": str(user.company_id),
    }
