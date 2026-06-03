# `/v3/finance/transaction/list` — baseline structure

**Зачем:** Ozon changelog (dev.ozon.ru) — 6 июля 2026 меняется endpoint.
На нём весь P&L, хранение, рекламный расход. Без baseline-snapshot мы
узнаем о breaking changes только когда P&L сломается в проде.

**Snapshot снят:** 2026-06-03, кабинет KOO/home.

## Request

```
POST /v3/finance/transaction/list
Headers: Client-Id, Api-Key, Content-Type: application/json
Body:
{
  "filter": {
    "date": {"from": "2026-05-27T00:00:00Z", "to": "2026-06-03T23:59:59Z"},
    "operation_type": [],
    "posting_number": "",
    "transaction_type": "all"
  },
  "page": 1,
  "page_size": 20
}
```

## Response.result.operations[] (ожидаемые поля)

Каждая операция содержит **13 ключей** (срез на 2026-06-03):

```
accruals_for_sale    # float или null. Главное поле для seller_revenue.
amount               # float. Отрицательное = расход, положительное = приток.
delivery_charge      # float
items                # array — список SKU в отправлении (для delivered)
operation_date       # string "YYYY-MM-DD HH:MM:SS" (без timezone!)
operation_id         # int. PK для дедупа в нашей БД.
operation_type       # string. Enum (OperationItemReturn / OperationLabelOriginal / ...)
operation_type_name  # string (RU имя для UI)
posting              # {delivery_schema, order_date, posting_number, warehouse_id}
return_delivery_charge  # float
sale_commission      # float или null
services             # array of {name, price} — детальные удержания
type                 # string ("services" / "orders" / ...)
```

## services[] (когда заполнен)

```
{name: "MarketplaceServiceItem...", price: -13.21}
```

Имена в `name` — стабильные ключи Ozon, по ним классификатор
(`services/transaction_classifier.py`) раскладывает в bucket'ы
(delivery_to_customer / storage / acquiring / advertising / etc).

## Полевые риски на 6 июля

| Поле | Если изменится | Что сломается |
|---|---|---|
| `operation_id` | Переименование → PK сломан | `on_conflict_do_nothing` начнёт дублировать строки |
| `accruals_for_sale` | Удаление / nullable change | **seller_revenue в P&L** обвалится |
| `services[].name` | Новые имена сервисов | classifier их не узнает → расходы попадут в "unknown" |
| `services[].price` | Тип/знак | `abs(price)` в bucket-распределении |
| `operation_date` | Format/timezone | `_parse_dt` упадёт или сдвинет время |
| `posting.posting_number` | Удаление | `posting_number` колонка станет NULL → drill-down по postings |

## Watch-points в коде

- `app/workers/tasks/sync_finance.py:282-308` — парсинг каждой operation
- `app/services/transaction_classifier.py:_BUCKET_MAP` — классификация services[].name
- `app/services/transaction_classifier.py:_OP_TYPE_BUCKET_MAP` — fallback по operation_type

## Schema validator

В sync_finance добавлен `_validate_op_schema(op)` который проверяет
наличие обязательных полей и логирует warning через `log.warning`
со счётчиком missing-fields. Если 6 июля поля исчезнут — будет видно
в логах worker до того как P&L соломается на UI.
