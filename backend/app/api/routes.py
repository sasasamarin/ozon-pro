"""
Главный API роутер.

Объединяет все endpoints (auth, products, orders, dashboard, etc.)

RBAC v2: к роутам прицеплен `Depends(require_module(slug))`, который
кидает 403, если у пользователя slug-а нет в `allowed_modules`.
OWNER/ADMIN — всегда видят всё.
"""
from fastapi import APIRouter, Depends

from app.api.deps_rbac import require_module
from app.api.endpoints import (
    account_balance,
    ad_campaign_stats,
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
    alerts,
    loans,
    loans_schedule,
    loans_cashflow_impact,
    loans_refinance,
    procurement_calendar,
    procurement_quality,
    reverse_funnel,
    sales_plans,
    product_stats,
    seasonality,
    ai_chat,
    ai_chat_v2,
    ai_bridge,
    storage_warning,
    competitor,
    competitor_prices,
    margin,
    taxes,
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


def _mod(slug: str):
    """shortcut: list of dependencies, что вешаем на роуты модуля."""
    return [Depends(require_module(slug))]


# === Auth/team/cabinets — без модульного гейта (или с собственным) ===
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(
    ozon_accounts.router, prefix="/ozon-accounts", tags=["ozon-accounts"],
    dependencies=_mod("cabinets"),
)
api_router.include_router(team.router, prefix="/team", tags=["team"],
    dependencies=_mod("team"),
)

# === Dashboard ===
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"],
    dependencies=_mod("dashboard"),
)
api_router.include_router(
    dashboard_v2.router, prefix="/dashboard/v2", tags=["dashboard"],
    dependencies=_mod("dashboard"),
)
api_router.include_router(
    ad_campaign_stats.router, prefix="/ads", tags=["ads"],
    dependencies=_mod("dashboard"),
)
api_router.include_router(
    dashboard_builder.router, prefix="/dashboard/builder", tags=["dashboard"],
    dependencies=_mod("dashboard"),
)

# === Products ===
api_router.include_router(products.router, prefix="/products", tags=["products"],
    dependencies=_mod("products"),
)
api_router.include_router(
    product_economics.router, prefix="/products/economics", tags=["products"],
    dependencies=_mod("products"),
)
api_router.include_router(
    calculator.router, prefix="/products/calculator", tags=["products"],
    dependencies=_mod("products"),
)
api_router.include_router(
    categories.router, prefix="/products/categories", tags=["products"],
    dependencies=_mod("products"),
)
api_router.include_router(
    product_stats.router, prefix="/products/stats", tags=["products"],
    dependencies=_mod("products"),
)
api_router.include_router(
    competitor_prices.router, prefix="/competitor-prices", tags=["products"],
    dependencies=_mod("products"),
)

# === Orders / returns ===
api_router.include_router(orders.router, prefix="/orders", tags=["orders"],
    dependencies=_mod("orders"),
)
api_router.include_router(returns.router, prefix="/returns", tags=["orders"],
    dependencies=_mod("orders"),
)

# === Finance ===
api_router.include_router(
    transactions.router, prefix="/finance/transactions", tags=["finance"],
    dependencies=_mod("finance"),
)
api_router.include_router(margin.router, prefix="/margin", tags=["finance"],
    dependencies=_mod("finance"),
)
api_router.include_router(taxes.router, prefix="/taxes", tags=["finance"],
    dependencies=_mod("finance"),
)
api_router.include_router(pnl.router, prefix="/finance/pnl", tags=["finance"],
    dependencies=_mod("finance"),
)
api_router.include_router(
    unit_economy.router, prefix="/finance/unit-economy", tags=["finance"],
    dependencies=_mod("finance"),
)
api_router.include_router(
    cashflow.router, prefix="/finance/cashflow", tags=["finance"],
    dependencies=_mod("finance"),
)
api_router.include_router(expenses.router, prefix="/finance/expenses", tags=["finance"],
    dependencies=_mod("finance"),
)
api_router.include_router(
    account_balance.router, prefix="/finance/account-balance", tags=["finance"],
    dependencies=_mod("finance"),
)
api_router.include_router(
    reconciliation.router, prefix="/reconciliation", tags=["finance"],
    dependencies=_mod("finance"),
)
api_router.include_router(costs.router, prefix="/costs", tags=["finance"],
    dependencies=_mod("finance"),
)

# === Loans ===
api_router.include_router(credit.router, prefix="/credit", tags=["loans"],
    dependencies=_mod("loans"),
)
api_router.include_router(loans.router, prefix="/loans", tags=["loans"],
    dependencies=_mod("loans"),
)
api_router.include_router(loans_schedule.router, prefix="/loans", tags=["loans"],
    dependencies=_mod("loans"),
)
api_router.include_router(loans_cashflow_impact.router, prefix="/loans", tags=["loans"],
    dependencies=_mod("loans"),
)
api_router.include_router(loans_refinance.router, prefix="/loans", tags=["loans"],
    dependencies=_mod("loans"),
)

# === Analytics ===
api_router.include_router(
    funnel.router, prefix="/analytics/funnel", tags=["analytics"],
    dependencies=_mod("analytics"),
)
api_router.include_router(
    funnel_v2.router, prefix="/analytics/funnel/v2", tags=["analytics"],
    dependencies=_mod("analytics"),
)
api_router.include_router(
    seasonality.router, prefix="/seasonality", tags=["analytics"],
    dependencies=_mod("analytics"),
)
api_router.include_router(
    storage_warning.router, prefix="/storage-warning", tags=["analytics"],
    dependencies=_mod("analytics"),
)
api_router.include_router(
    competitor.router, prefix="/competitor", tags=["analytics"],
    dependencies=_mod("analytics"),
)
api_router.include_router(
    day_explanation.router, prefix="/analytics/day-explanation", tags=["analytics"],
    dependencies=_mod("analytics"),
)
api_router.include_router(
    inventory_balance.router, prefix="/inventory", tags=["analytics"],
    dependencies=_mod("analytics"),
)
api_router.include_router(
    metrics_matrix.router, prefix="/analytics/metrics-matrix", tags=["analytics"],
    dependencies=_mod("analytics"),
)
api_router.include_router(
    whatif.router, prefix="/whatif", tags=["analytics"],
    dependencies=_mod("analytics"),
)
api_router.include_router(summary.router, prefix="/analytics/summary", tags=["analytics"],
    dependencies=_mod("analytics"),
)
api_router.include_router(
    reverse_funnel.router, prefix="/analytics/reverse-funnel", tags=["analytics"],
    dependencies=_mod("analytics"),
)
api_router.include_router(
    warehouse_stocks.router, prefix="/warehouse-stocks", tags=["analytics"],
    dependencies=_mod("analytics"),
)

# === Sales plan ===
api_router.include_router(
    plan_vs_fact.router, prefix="/analytics/plan-vs-fact", tags=["sales-plan"],
    dependencies=_mod("sales-plan"),
)
api_router.include_router(
    sales_plans.router, prefix="/plans", tags=["sales-plan"],
    dependencies=_mod("sales-plan"),
)
api_router.include_router(
    plan_purchase.router, prefix="/analytics/plan-purchase", tags=["procurement"],
    dependencies=_mod("procurement"),
)

# === Procurement ===
api_router.include_router(
    supply_params.router, prefix="/supply-params", tags=["procurement"],
    dependencies=_mod("procurement"),
)
api_router.include_router(
    recommendations.router, prefix="/recommendations", tags=["procurement"],
    dependencies=_mod("procurement"),
)
api_router.include_router(
    supplier_orders.router, prefix="/procurement/orders", tags=["procurement"],
    dependencies=_mod("procurement"),
)
api_router.include_router(supplies.router, prefix="/supplies", tags=["procurement"],
    dependencies=_mod("procurement"),
)
api_router.include_router(
    procurement_calendar.router, prefix="/procurement/calendar", tags=["procurement"],
    dependencies=_mod("procurement"),
)
api_router.include_router(
    procurement_quality.router, prefix="/procurement/quality", tags=["procurement"],
    dependencies=_mod("procurement"),
)

# === AI ===
api_router.include_router(
    ai_chat.router, prefix="/ai", tags=["ai"],
    dependencies=_mod("ai"),
)
api_router.include_router(
    ai_chat_v2.router, prefix="/ai", tags=["ai"],
    dependencies=_mod("ai"),
)
api_router.include_router(
    ai_context.router, prefix="/ai", tags=["ai"],
    dependencies=_mod("ai"),
)
# AI Bridge — для внешнего ozon-pro-ai (Render). Защищён SERVICE_TOKEN, модуль не вешаем.
api_router.include_router(
    ai_bridge.router, prefix="", tags=["ai-bridge"]
)

# === Alerts / settings / system ===
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"],
    dependencies=_mod("alerts"),
)
api_router.include_router(markers.router, prefix="/markers", tags=["alerts"],
    dependencies=_mod("alerts"),
)
api_router.include_router(
    communications.router, prefix="/communications", tags=["alerts"],
    dependencies=_mod("alerts"),
)
api_router.include_router(
    company_settings.router, prefix="/company/settings", tags=["settings"],
    dependencies=_mod("settings"),
)
api_router.include_router(
    system_health.router, prefix="/system", tags=["system"]
)
api_router.include_router(email_logs.router, prefix="/email", tags=["settings"],
    dependencies=_mod("settings"),
)
