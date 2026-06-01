# Диагностика «кредитов» в Ozon API — ШАГ 1

Дата: 2026-06-01
Источники: `transactions` (= `/v3/finance/transaction/list`), `ozon_financing`, `ozon_financing_movements`.
Период: `2025-01-01 … 2026-06-01` (всё, что есть в БД, 397 движений финансирования).

## 1. Поиск по ключевым словам ТЗ

Прямой ILIKE по `operation_type` и `operation_type_name`:

```sql
... WHERE operation_type   ILIKE '%credit%' OR '%loan%' OR '%invest%'
       OR operation_type_name ILIKE '%кредит%' OR '%займ%' OR '%заём%'
                              OR '%погашен%' OR '%invest%';
→ 0 строк
```

**Слов «кредит / займ / заём / Invest / погашение» в transaction/list НЕТ ВООБЩЕ.**
Ozon.Invest (заём от банка-партнёра, случай B из ТЗ) **через Seller API не отдаётся**.

## 2. Что найдено: три кандидата по словам «досрочн / выплат / рассрочка»

| operation_type | operation_type_name | rows | sum, ₽ | период |
|---|---|--:|--:|---|
| `OperationMarketplaceFlexiblePaymentSchedule` | Начисление за гибкий график выплат | **283** | −1 503 829 | 2025-01-24 … 2026-05-07 |
| `OperationMarketplaceServiceEarlyPaymentAccrual` | Услуга досрочной выплаты | **114** | −1 487 843 | 2025-01-24 … 2026-05-08 |
| `MarketplaceSellerInstallmentOperation` | Ozon Рассрочка | **112** | −89 769 | 2025-01-02 … 2025-02-21 |

Все три типа — **только отрицательные amount** (удержания); 0 положительных строк → выдачи тела займа в API нет.

## 3. Структура одной записи каждого типа (полный raw_data из БД)

### 3.1. `OperationMarketplaceFlexiblePaymentSchedule` — «Начисление за гибкий график выплат»

```json
{
  "time": "2026-05-07T00:00:00+00:00",
  "ozon_transaction_id": "50804447036",
  "operation_type": "OperationMarketplaceFlexiblePaymentSchedule",
  "operation_type_name": "Начисление за гибкий график выплат",
  "amount": -104.11,
  "description": "services",
  "posting_number": "",
  "raw_data": {
    "operation_id": 50804447036,
    "operation_date": "2026-05-07 00:00:00",
    "delivery_charge": 0,
    "return_delivery_charge": 0,
    "accruals_for_sale": 0,
    "sale_commission": 0,
    "amount": -104.11,
    "type": "services",
    "posting": {"delivery_schema": "", "order_date": "", "posting_number": "", "warehouse_id": 0},
    "items": [],
    "services": []
  }
}
```

→ `posting` пустой, `items=[]`, `services=[]`. **Никаких полей «principal», «interest», «тело», «процент» нет.** Одна суммарная цифра `amount`.

### 3.2. `OperationMarketplaceServiceEarlyPaymentAccrual` — «Услуга досрочной выплаты»

```json
{
  "time": "2026-05-08T00:00:00+00:00",
  "ozon_transaction_id": "50870440339",
  "operation_type": "OperationMarketplaceServiceEarlyPaymentAccrual",
  "operation_type_name": "Услуга досрочной выплаты",
  "amount": -186.96,
  "raw_data": {
    "operation_id": 50870440339,
    "operation_date": "2026-05-08 00:00:00",
    "amount": -186.96,
    "type": "services",
    "posting": {"delivery_schema": "", "order_date": "", "posting_number": "", "warehouse_id": 0},
    "items": [],
    "services": []
  }
}
```

→ Структурно **идентично** 3.1: одна сумма, без posting/items/services, без principal/interest.

### 3.3. `MarketplaceSellerInstallmentOperation` — «Ozon Рассрочка»

```json
{
  "time": "2025-02-21T00:00:00+00:00",
  "ozon_transaction_id": "29893611359",
  "operation_type": "MarketplaceSellerInstallmentOperation",
  "operation_type_name": "Ozon Рассрочка",
  "amount": -550.62,
  "description": "services",
  "posting_number": "59438467-0028-1",
  "raw_data": {
    "operation_id": 29893611359,
    "operation_date": "2025-02-21 00:00:00",
    "amount": -550.62,
    "type": "services",
    "posting": {"delivery_schema": "FBO", "posting_number": "59438467-0028-1", "warehouse_id": 1020000241710000},
    "items": [{"name": "Люстра…", "sku": 1346755624}],
    "services": [{"name": "MarketplaceServiceItemInstallment", "price": -550.62}]
  },
  "acquiring": 550.62   // ⚠ ВЖНО: уже распределено как эквайринг
}
```

→ Привязано к **posting + items** (заказ покупателя), **уже падает в колонку `acquiring`** в transactions. Это случай **C из ТЗ** (рассрочка покупателя) — на нашей стороне обычная услуга, как эквайринг. **Не заём.**

## 4. Таблицы `ozon_financing` / `ozon_financing_movements`

### 4.1. ozon_financing — 6 «договоров»

| product_type | rows | sum principal, ₽ | interest_rate | due_date |
|---|--:|--:|---|---|
| `early_payout` | 3 | 1 487 843 | **NULL** | **NULL** |
| `commission_installment` | 3 | 1 503 830 | **NULL** | **NULL** |

Все `source='ozon_api'`, `status='repaying'`. Ни одного `early_payout` или `commission_installment` со ставкой или сроком — Ozon API эти поля **не отдаёт**.

### 4.2. ozon_financing_movements — 397 строк, ВСЕ `movement_type='withholding'`

Сумма по типам:
- 283 строки `OperationMarketplaceFlexiblePaymentSchedule`, sum = 1 503 829 ₽
- 114 строк `OperationMarketplaceServiceEarlyPaymentAccrual`, sum = 1 487 843 ₽
- Σ = **397 строк = 397 ровно** ⇒ это **зеркало transactions**, не отдельная сущность.

⚠ **РИСК ДВОЙНОГО СЧЁТА.** Если P&L / воронка суммирует И `transactions`, И `ozon_financing_movements` (где `affects_pnl=t`), услуги досрочной выплаты и гибкого графика будут учтены дважды (~3 М ₽). Это, скорее всего, и есть «сумма мешает в воронке», про которую написал пользователь.

`ozon_financing.principal` тоже **не «тело займа»**, а агрегированная сумма уже начисленных удержаний по этой услуге. Использовать `principal` как обязательство по займу **нельзя** — это исторический оборот, а не остаток долга.

## 5. Выводы по случаям A/B/C из ТЗ

| Случай | Что в API | Как обрабатывать |
|---|---|---|
| **A. Услуга досрочной выплаты** (`Early`/`Flexible`) | Одна сумма, **без principal/interest, без posting** | Просто строка расхода в P&L и ДДС. Никакого разделения тело/процент. |
| **B. Заём Ozon.Invest (банк)** | **НЕТ в API ВООБЩЕ** (ни transactions, ни financing) | **Только вручную** (loans + loan_payments из ТЗ, Ветка 1) |
| **C. Ozon Рассрочка покупателя** | Привязка к posting+item, попадает в колонку `acquiring` | Уже корректно обрабатывается, ничего трогать не нужно |

## 6. Действия, которые потребуются на ШАГЕ 2

1. **Дедупликация:** убрать двойной счёт между `transactions` и `ozon_financing_movements` (или пометить movements `affects_pnl=false`, или убрать их из P&L-агрегата). Это объяснит «мешающую сумму в воронке».
2. **Случай A → P&L строка «Услуги ускоренного вывода»** (Flexible + Early, ~3 М ₽ за 16 мес). Никакого разделения тело/процент — его нет.
3. **Случай B (Ozon.Invest) → Ветка 1 ТЗ** — таблицы `loans` + `loan_payments` для ручного ведения. Это P0 для корректной прибыли, если у пользователя есть настоящий заём от банка.
4. **Случай C → ничего**, уже работает.
5. Переименовать UI-блок «Кредиты Ozon» в «Услуги ускоренного вывода» — текущее название вводит в заблуждение, никаких «кредитов» Ozon в API нет.

К ШАГУ 2 (модель) не перехожу до подтверждения.
