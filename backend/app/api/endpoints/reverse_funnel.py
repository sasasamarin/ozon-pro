"""
/analytics/reverse-funnel — «задай цель → как её достичь?».

POST /solve body:
  { product_id, target_metric: 'revenue'|'orders'|'net_profit'|'delivered',
    target_value, days?: 60 }

Возвращает 3 сценария (трафик / реклама / цена) с required-input
и предсказанным исходом из WhatIf engine.
"""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.services.reverse_funnel import scenario_to_dict, solve_for_target
from app.services.whatif_engine import (
    ScenarioInput,
    compute_betas,
    simulate_scenario,
)

router = APIRouter()


class ReverseFunnelRequest(BaseModel):
    product_id: uuid.UUID
    target_metric: Literal["revenue", "orders", "net_profit", "delivered"]
    target_value: float = Field(..., gt=0)
    days: int = Field(60, ge=7, le=365)


@router.post("/solve")
async def solve_reverse_funnel(
    body: ReverseFunnelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    prod = (await db.execute(text("""
        SELECT p.id, p.name, p.offer_id, p.cost_price::float cost,
               p.marketing_price::float, p.current_price::float,
               p.sales_percent_fbo::float comm_pct
        FROM products p JOIN ozon_accounts a ON a.id = p.ozon_account_id
        WHERE p.id = :pid AND a.company_id = :cid
    """), {"pid": str(body.product_id), "cid": str(current_user.company_id)})).first()
    if not prod:
        raise HTTPException(404, "product not found")

    cost = prod.cost or 0.0
    seller_price = prod.marketing_price or prod.current_price or 0.0
    commission_pct = prod.comm_pct or 25.0

    company = (await db.execute(text("""
        SELECT tax_regime, tax_rate_pct, vat_rate_pct FROM companies WHERE id=:cid
    """), {"cid": str(current_user.company_id)})).first()
    tax_regime = company.tax_regime or "usn_income"
    tax_rate = float(company.tax_rate_pct or 6.0)
    vat_rate = float(company.vat_rate_pct) if company.vat_rate_pct else None

    betas = await compute_betas(db, product_id=body.product_id, days=body.days)

    base_inp = ScenarioInput(name="Текущее")
    base_out = simulate_scenario(
        base=betas.base, seller_price=seller_price, cost=cost,
        commission_pct=commission_pct, tax_regime=tax_regime,
        tax_rate=tax_rate, vat_rate=vat_rate, betas=betas,
        scenario=base_inp, base_net_profit=0,
    )

    scenarios = []
    for lever in ("impressions", "ad_spend", "seller_price"):
        sc = solve_for_target(
            lever=lever,
            target_metric=body.target_metric,
            target_value=body.target_value,
            base=betas.base, seller_price=seller_price, cost=cost,
            commission_pct=commission_pct, tax_regime=tax_regime,
            tax_rate=tax_rate, vat_rate=vat_rate, betas=betas,
            base_net_profit=base_out.net_profit,
        )
        scenarios.append(scenario_to_dict(sc))

    return {
        "product_id": str(body.product_id),
        "product_name": prod.name,
        "offer_id": prod.offer_id,
        "target_metric": body.target_metric,
        "target_value": body.target_value,
        "days_analyzed": body.days,
        "base": {
            "revenue":     base_out.revenue,
            "orders":      base_out.orders,
            "delivered":   base_out.delivered,
            "net_profit":  base_out.net_profit,
            "ad_spend":    base_out.ad_spend,
            "seller_price": base_out.seller_price,
            "impressions": base_out.impressions,
        },
        "scenarios": scenarios,
    }
