"""
Настройки компании — пока только налоговый режим.
Влияет на расчёт чистой прибыли в Экономике/P&L/Cashflow.

GET  /api/v1/company/settings           — текущие настройки
PATCH /api/v1/company/settings          — обновить
GET  /api/v1/company/settings/tax/preview?gross_margin=...  — превью «сколько съест налог»
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Company, User


router = APIRouter()


TAX_REGIMES = {
    "usn_income": {
        "label": "УСН Доходы",
        "default_rate": 6.0,
        "description": "Платишь % от ВЫРУЧКИ (= seller_price × qty доставленных).",
        "applies_to": "revenue",
    },
    "usn_income_minus": {
        "label": "УСН Доходы-Расходы",
        "default_rate": 15.0,
        "description": "Платишь % от ПРИБЫЛИ (выручка − себест − комиссия − реклама − логистика).",
        "applies_to": "profit",
    },
    "osno": {
        "label": "ОСНО (общая)",
        "default_rate": 20.0,
        "description": "Налог на прибыль 20% + НДС с выручки (по ставке).",
        "applies_to": "profit",
    },
    "none": {
        "label": "Без налога",
        "default_rate": 0.0,
        "description": "Для тестов или ИП на патенте/НПД.",
        "applies_to": "none",
    },
}


class TaxSettings(BaseModel):
    tax_regime: str
    tax_rate_pct: float
    vat_rate_pct: float | None = None


class CompanySettings(BaseModel):
    name: str
    inn: str | None
    tax: TaxSettings


class TaxRegimeInfo(BaseModel):
    code: str
    label: str
    default_rate: float
    description: str
    applies_to: str


@router.get("/regimes", response_model=list[TaxRegimeInfo])
async def list_tax_regimes() -> list[TaxRegimeInfo]:
    """Справочник доступных налоговых режимов (без авторизации — статика)."""
    return [TaxRegimeInfo(code=k, **v) for k, v in TAX_REGIMES.items()]


@router.get("/", response_model=CompanySettings)
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompanySettings:
    company = (await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )).scalar_one()
    return CompanySettings(
        name=company.name,
        inn=company.inn,
        tax=TaxSettings(
            tax_regime=company.tax_regime or "usn_income",
            tax_rate_pct=float(company.tax_rate_pct or 6.0),
            vat_rate_pct=float(company.vat_rate_pct) if company.vat_rate_pct is not None else None,
        ),
    )


class UpdateSettingsBody(BaseModel):
    tax_regime: str | None = None
    tax_rate_pct: float | None = Field(default=None, ge=0, le=100)
    vat_rate_pct: float | None = Field(default=None, ge=0, le=100)


@router.patch("/", response_model=CompanySettings)
async def update_settings(
    body: UpdateSettingsBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompanySettings:
    if body.tax_regime and body.tax_regime not in TAX_REGIMES:
        raise HTTPException(400, f"Unknown tax_regime; allowed: {list(TAX_REGIMES.keys())}")
    company = (await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )).scalar_one()
    if body.tax_regime is not None:
        company.tax_regime = body.tax_regime
        # Если режим сменили без явного rate — подставим дефолт режима
        if body.tax_rate_pct is None:
            company.tax_rate_pct = TAX_REGIMES[body.tax_regime]["default_rate"]
    if body.tax_rate_pct is not None:
        company.tax_rate_pct = body.tax_rate_pct
    if body.vat_rate_pct is not None:
        company.vat_rate_pct = body.vat_rate_pct
    await db.commit()
    return await get_settings(current_user=current_user, db=db)
