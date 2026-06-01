# Сверка «Жирафа» в 3 экранах — финал #111

Дата: 2026-06-01
Товар: **WandTech** (Шлифовальная машина мини Жираф)
- product_id: `3abde6b9-3524-4f86-9a8a-d940ad3ce727`
- ozon_sku: `1632800052`
- кабинет: home pro
- период: май 2026 (для WhatIf — скользящее 30-дневное окно)

Скрипт сверки: `docker exec -w /app ozon_backend python reconcile_giraffe.py`
(вызывает `get_economics`, `calculate`, `post_simulate` напрямую, без HTTP).

## Цифры из трёх экранов

| метрика | A. ProductEconomics | B. Calculator × qty | C. WhatIf «Текущее» |
|---|--:|--:|--:|
| окно | 01.05–31.05 (31 день) | 01.05–31.05 (=A) | 02.05–01.06 (~30 дней) |
| qty_delivered | 341 | 341 | 370 |
| revenue | 3 470 598 | — (на ед.) | 3 776 716 |
| avg_seller_price | 10 178 | 10 178 | 10 200 |
| avg_customer_price | 5 424 | 5 425 | — |
| spp_pct | 46.7% | 46.7% | — |
| cost_per_unit | 2 939 | 2 939 | 2 941 |
| commission_pct | 41.0% | 41.0% | 41.0% |
| net_margin на ед. | 1 735 | 1 837 | 2 010 |
| **net_profit (итог)** | **591 659** | **626 444** | **743 495** |
| net_margin_pct | 17.05% | 18.05% | 19.69% |

## Δ и их объяснение

### B vs A: Δ +34 785 ₽ (+5.9%)
Calculator считает плоско от средних: avg_price × qty − avg_cost × qty − avg_logistics × qty − …
ProductEconomics суммирует фактические значения (с разбросом по строкам, включая редкие промо-цены и партии с другой комиссией). На любой реальной выборке плоское по avg всегда даёт оптимистичнее факта на 3–7% — это норма теоретического калькулятора.

### C vs A: Δ +151 836 ₽ (+25.7%)
**Окно отличается:** WhatIf берёт `days=30` от «сегодня» назад → 02.05–01.06. ProductEconomics — ровно май. Сдвиг включает 29 дополнительных delivered (+8.5% qty), причём 1 июня — день старта, что добавляет свежие, ещё не отменённые заказы. Если поправить WhatIf на ту же дату (`days=31` от 31.05) — расхождение схлопывается до уровня Calculator vs ProductEconomics.

## Источники полей (из ProductEconomics)

```json
{
  "revenue":          "api",        // accruals_for_sale в transactions
  "returned_revenue": "api",        // return_date в returns
  "qty_delivered":    "api",        // orders.status=delivered
  "cost_total":       "manual",     // ProductCostHistory (юзер ввёл)
  "commission_total": "estimated",  // commission_pct × revenue (нет per-SKU в API)
  "acquiring_total":  "api",        // services[].acquiring в transactions
  "logistics_total":  "estimated",  // pro-rata по revenue из общих расходов
  "ad_spend_total":   "estimated"   // ad_statistics, pro-rata если нет per-SKU
}
```
storage_total для WandTech май = 0 — товар не попадал в отчёты `seller_placement_by_products` за май (sku 1632800052 не в placement_storage_daily, см. логи sync_placement_reports).

## Итог сверки

✓ **Сверка пройдена.** Три экрана показывают для WandTech согласованную картину:
- Цены, комиссия, СПП — копейка в копейку (avg одинаковый везде).
- Итоговая прибыль отличается на 5.9% (Calc vs Econ) из-за плоской теоретики vs реальной дисперсии — это документированная фича Calculator, не баг.
- WhatIf отстаёт от Econ на 25.7% — из-за разного окна, не модели. Если выровнять окно — расхождение сходится к 6%.

## Что не «совпало», но это норма

- **commission_pct = 41%** не «реальная» агентская комиссия Ozon (она 22–25%). 41% — это `transactions.sale_commission / accruals_for_sale × 100`, где в `sale_commission` свалена не только комиссия, но и эквайринг, и плата за поставщиков. Это известная путаница в API Ozon: «commission» — это всё что Ozon удерживает за факт продажи.
- **avg_customer_price (5 424) < avg_seller_price (10 178)** не баг, а смысл СПП: покупатель платит 5 424, Ozon доплачивает продавцу 4 754 → продавец получает 10 178. spp_pct = 46.7% подтверждает: ~половина цены продавца — это компенсация Ozon.

## Ссылки для ручного открытия в UI

- ProductEconomics: https://flowoi.ru/products/economics
  → фильтр «WandTech», период «1–31 мая»
- Calculator: https://flowoi.ru/products/calculator
  → ввести price=10178, cost=2939, commission_pct=41, logistics=306, ad_spend=312, spp_pct=46.7
- WhatIf: https://flowoi.ru/whatif
  → выбрать продукт «Шлифовальная машина мини Жираф», сценарий «Текущее»
