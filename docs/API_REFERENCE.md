# Flowoi API Reference

Автогенерация из FastAPI OpenAPI spec на 2026-06-01. **117 endpoint** в **26 группах**.

`*` = обязательный параметр. `+body` = JSON body.

Все endpoint требуют JWT auth (header `Authorization: Bearer <token>`) кроме `/auth/login`, `/auth/register`, `/system/health`.

## auth

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `POST` | `/api/v1/auth/login` | Login |  +body |
| `GET` | `/api/v1/auth/me` | Get Me | — |
| `PATCH` | `/api/v1/auth/me` | Update Me |  +body |
| `POST` | `/api/v1/auth/register` | Register |  +body |

## ozon-accounts

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/ozon-accounts/` | List Ozon Accounts | — |
| `POST` | `/api/v1/ozon-accounts/` | Create Ozon Account |  +body |
| `POST` | `/api/v1/ozon-accounts/test-perf-credentials` | Test Performance Credentials |  +body |
| `DELETE` | `/api/v1/ozon-accounts/{account_id}` | Delete Ozon Account | `account_id*: string` |
| `GET` | `/api/v1/ozon-accounts/{account_id}` | Get Ozon Account | `account_id*: string` |
| `PATCH` | `/api/v1/ozon-accounts/{account_id}` | Update Ozon Account | `account_id*: string` +body |
| `POST` | `/api/v1/ozon-accounts/{account_id}/sync` | Sync Ozon Account | `account_id*: string` |

## dashboard

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/dashboard/` | Get Dashboard | `days: integer`, `cabinet_ids: any` |
| `GET` | `/api/v1/dashboard/v2/` | Get Dashboard V2 | `date_from: any`, `date_to: any`, `days: integer`, `granularity: string`, `compare: string`, `cabinet_ids: any`, `top_limit: integer` |

## products

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/products/` | List Products | `cabinet_ids: any`, `cabinet_id: any`, `category_id: any`, `tags: any` |
| `PATCH` | `/api/v1/products/bulk/meta` | Patch Bulk Meta |  +body |
| `POST` | `/api/v1/products/calculator/calc` | Calculate |  +body |
| `GET` | `/api/v1/products/categories-list` | List Categories | — |
| `GET` | `/api/v1/products/categories/` | Get Categories | `days: integer`, `cabinet_ids: any` |
| `GET` | `/api/v1/products/categories/tree` | Get Categories Tree | `days: integer`, `cabinet_ids: any`, `hide_empty: boolean` |
| `GET` | `/api/v1/products/economics/` | Get Economics | `days: integer`, `date_from: any`, `date_to: any`, `cabinet_ids: any`, `product_id: any`, `category_id: any`, `tags: any`, `include_archived: boolean` |
| `GET` | `/api/v1/products/tags-list` | List Tags | — |
| `PATCH` | `/api/v1/products/{product_id}/meta` | Patch Product Meta | `product_id*: string` +body |
| `GET` | `/api/v1/products/{product_id}/stock-details` | Product Stock Details | `product_id*: string` |
| `GET` | `/api/v1/products/{product_id}/stock-sales` | Product Stock Sales | `product_id*: string`, `days: integer` |
| `GET` | `/api/v1/products/{product_id}/stocks` | Product Stocks | `product_id*: string` |

## orders

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/orders/` | List Orders | `page: integer`, `page_size: integer`, `cabinet_ids: any`, `date_from: any`, `date_to: any`, `status: any`, `order_type: any`, `search: any` |
| `GET` | `/api/v1/orders/daily` | Orders Daily | `days: integer`, `cabinet_ids: any` |

## finance

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/finance/account-balance/` | Get Balance | `days: integer`, `cabinet_ids: any` |
| `GET` | `/api/v1/finance/cashflow/` | Get Cashflow | `days: integer`, `granularity: string`, `cabinet_ids: any` |
| `GET` | `/api/v1/finance/expenses/` | List Expenses | `days: integer`, `category: any` |
| `POST` | `/api/v1/finance/expenses/` | Create Expense |  +body |
| `GET` | `/api/v1/finance/expenses/stats` | Expense Stats | `days: integer` |
| `DELETE` | `/api/v1/finance/expenses/{expense_id}` | Delete Expense | `expense_id*: string` |
| `GET` | `/api/v1/finance/pnl/` | Get Pnl | `days: integer`, `cabinet_ids: any`, `compare: boolean` |
| `GET` | `/api/v1/finance/transactions/` | List Transactions | `page: integer`, `page_size: integer`, `cabinet_ids: any`, `date_from: any`, `date_to: any`, `operation_type: any`, `search: any` |
| `GET` | `/api/v1/finance/transactions/daily` | Transactions Daily | `period*: string`, `cabinet_ids: any` |
| `GET` | `/api/v1/finance/transactions/export.csv` | Export Transactions Csv | `cabinet_ids: any`, `date_from: any`, `date_to: any`, `operation_type: any`, `search: any` |
| `GET` | `/api/v1/finance/transactions/monthly` | Transactions Monthly | `cabinet_ids: any`, `months_back: integer` |
| `GET` | `/api/v1/finance/transactions/types` | List Operation Types | `cabinet_ids: any` |
| `POST` | `/api/v1/finance/unit-economy/commit` | Commit Upload |  +body |
| `GET` | `/api/v1/finance/unit-economy/coverage` | Upload Coverage | `months_back: integer` |
| `POST` | `/api/v1/finance/unit-economy/preview` | Preview Upload |  +body |
| `GET` | `/api/v1/finance/unit-economy/status` | Upload Status | — |

## analytics

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/analytics/day-explanation/` | Explain Day | `date*: string`, `product_id: any`, `period_days: integer`, `cabinet_ids: any` |
| `GET` | `/api/v1/analytics/funnel/` | Get Funnel | `days: integer`, `cabinet_ids: any`, `compare: boolean` |
| `GET` | `/api/v1/analytics/funnel/products` | Funnel Top Products | `days: integer`, `cabinet_ids: any`, `sort: string`, `limit: integer`, `min_impressions: integer` |
| `GET` | `/api/v1/analytics/funnel/products/{product_id}` | Funnel Single Product | `product_id*: string`, `days: integer` |
| `GET` | `/api/v1/analytics/funnel/v2/` | Get Funnel V2 | `days: integer`, `date_from: any`, `date_to: any`, `product_id: any`, `product_ids: any`, `cabinet_ids: any`, `compare: string` |
| `GET` | `/api/v1/analytics/funnel/v2/ad-by-type` | Ad By Type | `days: integer`, `date_from: any`, `date_to: any`, `cabinet_ids: any` |
| `GET` | `/api/v1/analytics/funnel/v2/best-worst-days` | Best Worst Days | `days: integer`, `metric: string`, `product_id: any`, `product_ids: any`, `cabinet_ids: any` |
| `GET` | `/api/v1/analytics/funnel/v2/correlations` | Funnel Correlations | `days: integer`, `date_from: any`, `date_to: any`, `product_id: any`, `product_ids: any`, `cabinet_ids: any` |
| `GET` | `/api/v1/analytics/funnel/v2/daily` | Get Funnel Daily | `days: integer`, `date_from: any`, `date_to: any`, `product_id: any`, `product_ids: any`, `cabinet_ids: any` |
| `GET` | `/api/v1/analytics/funnel/v2/sankey` | Funnel Sankey | `days: integer`, `date_from: any`, `date_to: any`, `product_id: any`, `product_ids: any`, `cabinet_ids: any` |
| `GET` | `/api/v1/analytics/metrics-matrix/` | Get Metrics Matrix | `days: integer`, `date_from: any`, `date_to: any`, `granularity: string`, `metrics: any`, `product_id: any`, `cabinet_ids: any` |
| `GET` | `/api/v1/analytics/metrics-matrix/available` | List Available Metrics | — |
| `POST` | `/api/v1/analytics/plan-purchase/calculate` | Calculate Purchase Plan |  +body |
| `GET` | `/api/v1/analytics/plan-vs-fact/` | Get Pvf | `period_from: any`, `period_to: any`, `cabinet_ids: any` |
| `GET` | `/api/v1/analytics/plan-vs-fact/targets` | List Targets | — |
| `POST` | `/api/v1/analytics/plan-vs-fact/targets` | Create Target |  +body |
| `DELETE` | `/api/v1/analytics/plan-vs-fact/targets/{target_id}` | Delete Target | `target_id*: string` |
| `POST` | `/api/v1/analytics/reverse-funnel/solve` | Solve Reverse Funnel |  +body |
| `GET` | `/api/v1/analytics/summary/` | Get Summary | `days: integer` |

## whatif

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/whatif/betas/{product_id}` | Get Betas | `product_id*: string`, `days: integer` |
| `POST` | `/api/v1/whatif/simulate` | Post Simulate |  +body |

## credit

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/credit/list` | List Credits | — |
| `GET` | `/api/v1/credit/movements/{financing_id}` | List Movements | `financing_id*: string` |

## loans

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/loans` | List Loans | — |
| `POST` | `/api/v1/loans` | Create Loan |  +body |
| `GET` | `/api/v1/loans/aggregate/period` | Aggregate Period | `days: integer`, `date_from: any`, `date_to: any` |
| `DELETE` | `/api/v1/loans/{loan_id}` | Delete Loan | `loan_id*: string` |
| `GET` | `/api/v1/loans/{loan_id}/payments` | List Payments | `loan_id*: string` |
| `POST` | `/api/v1/loans/{loan_id}/payments` | Add Manual Payment | `loan_id*: string` +body |
| `POST` | `/api/v1/loans/{loan_id}/payments/{seq}/pay` | Mark Paid | `loan_id*: string`, `seq*: integer`, `paid_at: any` |

## returns

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/returns/` | List Returns | `kind: string`, `page: integer`, `page_size: integer`, `cabinet_ids: any`, `date_from: any`, `date_to: any`, `search: any` |
| `GET` | `/api/v1/returns/stats` | Returns Stats | `days: integer`, `cabinet_ids: any` |

## reconciliation

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/reconciliation/realization` | List Reconciliations | — |
| `POST` | `/api/v1/reconciliation/realization/run` | Run Reconciliation | `year: any`, `month: any` |
| `GET` | `/api/v1/reconciliation/realization/{year}/{month}` | Get Reconciliation Detail | `year*: integer`, `month*: integer` |
| `GET` | `/api/v1/reconciliation/status` | Reconciliation Status | — |

## procurement

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/procurement/orders/` | List Orders | `status: any`, `days: integer` |
| `POST` | `/api/v1/procurement/orders/` | Create Order |  +body |
| `GET` | `/api/v1/procurement/orders/suppliers` | List Suppliers | — |
| `POST` | `/api/v1/procurement/orders/suppliers` | Create Supplier |  +body |
| `DELETE` | `/api/v1/procurement/orders/{order_id}` | Delete Order | `order_id*: string` |
| `PATCH` | `/api/v1/procurement/orders/{order_id}` | Update Order | `order_id*: string` +body |
| `GET` | `/api/v1/supply-params/` | List Supply Params | — |
| `POST` | `/api/v1/supply-params/{product_id}` | Upsert Supply Params | `product_id*: string` +body |

## communications

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/communications/questions` | List Questions | `days: integer`, `only_unanswered: boolean` |
| `GET` | `/api/v1/communications/reviews` | List Reviews | `days: integer`, `rating: any` |

## markers

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/markers/` | List Markers | `days: integer`, `product_id: any`, `marker_type: any` |
| `POST` | `/api/v1/markers/` | Create Marker |  +body |
| `DELETE` | `/api/v1/markers/{marker_id}` | Delete Marker | `marker_id*: string` |

## team

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/team/invitations` | List Invitations | — |
| `POST` | `/api/v1/team/invitations` | Create Invitation |  +body |
| `DELETE` | `/api/v1/team/invitations/{invitation_id}` | Revoke Invitation | `invitation_id*: string` |
| `GET` | `/api/v1/team/members` | List Members | — |

## email

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/email/log` | List Email Log | `days: integer`, `status: any`, `limit: integer` |
| `GET` | `/api/v1/email/templates` | List Templates | — |
| `POST` | `/api/v1/email/test-send` | Test Send Email |  +body |

## settings

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/company/settings/` | Get Settings | — |
| `PATCH` | `/api/v1/company/settings/` | Update Settings |  +body |
| `GET` | `/api/v1/company/settings/regimes` | List Tax Regimes | — |

## inventory

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/inventory/balance` | Get Inventory Balance | `cabinet_ids: any`, `category_id: any`, `include_archived: boolean` |

## warehouses

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/warehouse-stocks/clusters` | Clusters Summary | — |
| `GET` | `/api/v1/warehouse-stocks/products/{product_id}` | Product Warehouse Stocks | `product_id*: string` |

## recommendations

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/recommendations/products` | List Recommendations | `cabinet_ids: any` |
| `GET` | `/api/v1/recommendations/products/{product_id}` | Get Recommendation | `product_id*: string` |

## system

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/system/health` | Get System Health | — |

## ai

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `POST` | `/api/v1/ai/ask` | Ai Ask |  +body |
| `GET` | `/api/v1/ai/context/{product_id}` | Product Full Context | `product_id*: string`, `days: integer` |

## costs

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/api/v1/costs/products` | List Product Costs | — |
| `POST` | `/api/v1/costs/products/{product_id}` | Update Product Cost | `product_id*: string` +body |
| `GET` | `/api/v1/costs/template.csv` | Download Template | — |
| `POST` | `/api/v1/costs/upload-csv` | Upload Costs Csv |  +body |

## root

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/` | Root | — |

## health

| Method | Path | Описание | Параметры |
|---|---|---|---|
| `GET` | `/health` | Health | — |
| `GET` | `/health/db` | Health Db | — |
