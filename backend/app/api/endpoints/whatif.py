"""
WhatIf endpoint — реальные эластичности per товар + симуляция сценариев.

GET  /api/v1/whatif/betas/{product_id}?days=60
POST /api/v1/whatif/simulate
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Company, Product, User
from app.services.whatif_engine import (
    BetasResult, ScenarioInput, compute_betas, simulate_scenario,
)
from app.services.tax import calc_tax

router = APIRouter()


@router.get("/betas/{product_id}")
async def get_betas(
    product_id: uuid.UUID,
    days: int = Query(60, ge=14, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Защита: товар должен принадлежать компании юзера
    prod = (await db.execute(text("""
        SELECT p.id, p.name, p.offer_id, p.ozon_sku, a.name AS cabinet_name,
               p.cost_price::float, p.marketing_price::float, p.current_price::float,
               p.sales_percent_fbo::float
        FROM products p JOIN ozon_accounts a ON a.id = p.ozon_account_id
        WHERE p.id = :pid AND a.company_id = :cid
    """), {"pid": str(product_id), "cid": str(current_user.company_id)})).first()
    if not prod:
        raise HTTPException(404, "product not found in your cabinets")

    betas = await compute_betas(db, product_id=product_id, days=days)

    def beta_dict(bp):
        return {
            "beta": bp.beta, "n": bp.n, "r2": bp.r2,
            "confidence": bp.confidence, "note": bp.note,
        }

    return {
        "product": {
            "id": str(product_id), "name": prod.name, "offer_id": prod.offer_id,
            "ozon_sku": prod.ozon_sku, "cabinet_name": prod.cabinet_name,
            "cost_price": prod.cost_price, "seller_price": prod.marketing_price,
            "commission_pct": prod.sales_percent_fbo or 25.0,
        },
        "period": {"days": days, "from": betas.period_from, "to": betas.period_to},
        "base": betas.base,
        "betas": {
            "funnel": {
                "imp_to_visits": beta_dict(betas.imp_to_visits),
                "visits_to_cart": beta_dict(betas.visits_to_cart),
                "cart_to_orders": beta_dict(betas.cart_to_orders),
                "orders_to_delivered": beta_dict(betas.orders_to_delivered),
                "imp_to_orders_overall": beta_dict(betas.imp_to_orders),
            },
            "price": {
                "seller_price_to_orders": beta_dict(betas.seller_price_to_orders),
                "customer_price_to_orders": beta_dict(betas.customer_price_to_orders),
            },
            "ad": {
                "ad_spend_to_imp": beta_dict(betas.ad_spend_to_imp),
                "ad_spend_to_orders": beta_dict(betas.ad_spend_to_orders),
            },
        },
    }


class ScenarioRequest(BaseModel):
    name: str
    ad_spend_pct: float = 0.0
    seller_price_pct: float = 0.0
    impressions_pct: float = 0.0
    cr_cart_to_order_pct: float = 0.0
    cost_pct: float = 0.0
    spp_pct: float | None = None
    override_beta_price: float | None = None
    override_beta_customer_price: float | None = None
    override_beta_ad_to_imp: float | None = None


class SimulateRequest(BaseModel):
    product_id: uuid.UUID
    days: int = 60
    scenarios: list[ScenarioRequest]


@router.post("/simulate")
async def post_simulate(
    body: SimulateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    prod = (await db.execute(text("""
        SELECT p.id, p.name, p.cost_price::float, p.marketing_price::float,
               p.current_price::float, p.sales_percent_fbo::float
        FROM products p JOIN ozon_accounts a ON a.id = p.ozon_account_id
        WHERE p.id = :pid AND a.company_id = :cid
    """), {"pid": str(body.product_id), "cid": str(current_user.company_id)})).first()
    if not prod:
        raise HTTPException(404, "product not found")

    cost = prod.cost_price or 0.0
    seller_price = prod.marketing_price or prod.current_price or 0.0
    commission_pct = prod.sales_percent_fbo or 25.0

    company = (await db.execute(select(Company).where(Company.id == current_user.company_id))).scalar_one()
    tax_regime = company.tax_regime or "usn_income"
    tax_rate = float(company.tax_rate_pct or 6.0)
    vat_rate = float(company.vat_rate_pct) if company.vat_rate_pct else None

    betas = await compute_betas(db, product_id=body.product_id, days=body.days)

    # Базовый сценарий (текущее состояние) — для дельты
    base_input = ScenarioInput(name="Текущее")
    base_out = simulate_scenario(
        base=betas.base, seller_price=seller_price, cost=cost,
        commission_pct=commission_pct, tax_regime=tax_regime,
        tax_rate=tax_rate, vat_rate=vat_rate, betas=betas,
        scenario=base_input, base_net_profit=0.0,
    )
    base_net = base_out.net_profit

    # Кастомные сценарии
    results = [base_out.__dict__]
    for sc_req in body.scenarios:
        sc_in = ScenarioInput(
            name=sc_req.name,
            ad_spend_pct=sc_req.ad_spend_pct,
            seller_price_pct=sc_req.seller_price_pct,
            impressions_pct=sc_req.impressions_pct,
            cr_cart_to_order_pct=sc_req.cr_cart_to_order_pct,
            cost_pct=sc_req.cost_pct,
            spp_pct=sc_req.spp_pct,
            override_beta_price=sc_req.override_beta_price,
            override_beta_customer_price=sc_req.override_beta_customer_price,
            override_beta_ad_to_imp=sc_req.override_beta_ad_to_imp,
        )
        out = simulate_scenario(
            base=betas.base, seller_price=seller_price, cost=cost,
            commission_pct=commission_pct, tax_regime=tax_regime,
            tax_rate=tax_rate, vat_rate=vat_rate, betas=betas,
            scenario=sc_in, base_net_profit=base_net,
        )
        # delta уже посчитан внутри
        out.delta_net_vs_base = round(out.net_profit - base_net, 2)
        results.append(out.__dict__)

    return {
        "product_id": str(body.product_id),
        "product_name": prod.name,
        "tax_regime_label": "УСН Доходы" if tax_regime == "usn_income" else tax_regime,
        "tax_rate_pct": tax_rate,
        "scenarios": results,
    }
