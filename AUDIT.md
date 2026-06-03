# Flowoi — аудит кодовой базы

> P1 #11 из мастер-брифа. Снапшот на 2026-06-03 после ~15 коммитов сессии.
> Каждая находка с `файл:строки` (по правилу `flowoi_audit_prompt.md`).

## Сводка

| Слой | Цифра |
|---|---|
| backend python-файлов | 160 |
| api endpoints | 50 файлов |
| frontend pages | 52 |
| TODO/FIXME/HACK | 18 |
| Заглушки `NotImplementedError` | 5 |
| Alembic миграции | 0001 → 0029 (29 шт) |

---

## 🔴 P0 — исправлено в этой же сессии

### 1. Magic `0.41` комиссия в AI tools

- **Было:** `backend/app/services/ai/tools_v2.py:340` использовал `comm_pct = 0.41`.
- **Контекст:** в `services/finance_consts.py:86` чёрным по белому: «41% было исторической ОШИБКОЙ из старого `reconcile_realization`», правильное значение **`DEFAULT_COMMISSION_PCT = 25.0`** (line 24).
- **Фикс (этот коммит):** в `unit_economics()` теперь импорт `DEFAULT_COMMISSION_PCT/ACQUIRING_PCT_DEFAULT/LOGISTICS_PER_UNIT_DEFAULT` из `finance_consts`. Магия удалена.

---

## 🟡 P1 — следующие правки (вне рамки этого аудита)

### 2. Дубль SQL «текущий остаток» в 5 местах

`WITH last_wh AS … last_agg AS … wh_sum AS … agg_sum AS …` повторяется в:
- `api/endpoints/products.py:116`
- `api/endpoints/storage_warning.py:103`
- `api/endpoints/inventory_balance.py:84`
- `services/analytics_engine.py:130`
- `services/ai/tools_v2.py:224`

**Риск:** при изменении логики (например, добавили warehouse_type='CROSSBORDER') придётся править 5 мест → расхождение между UI products и storage-warning.

**Рекомендация:** вынести в `services/stock_query.py:current_stock_cte()` — функция возвращает SQLAlchemy `text()` фрагмент или Pythonовский dict per product_id. Каждый из 5 endpoint-ов делает `JOIN cte`.

### 3. Дубль логики «выручка» в 30+ endpoints

`OrderItem.total_price`, `Order.total_amount`, `AnalyticsDaily.revenue`, `Transaction.accruals_for_sale` — четыре разных источника, и каждый endpoint выбирает свой. Юзер видит разные числа в dashboard/funnel/orders/p&l.

- pnl.py — единственный с правильным `seller_revenue` (P0 #2)
- DashboardBuilder теперь имеет `seller_revenue` как отдельную метрику (фикс этой сессии)
- Funnel/Orders/Categories — всё ещё buyer-side

**Рекомендация:** глобальный helper `services/revenue_views.py` с тремя функциями: `seller_revenue_for(...)`, `buyer_revenue_for(...)`, `ordered_value_for(...)` и явный source-флаг в response каждого endpoint.

### 4. TODO долгожители

В кодовой базе **18 TODO/FIXME**. Болевые точки:

| Файл:строка | TODO | Возраст | Приоритет |
|---|---|---|---|
| `services/reports.py:30,38,46` | Реальная реализация финансовых отчётов Ozon (request/poll/download/parse) — сейчас 3 функции возвращают `None`/`{}` | Phase 1 (давно) | P1 — `reconciliation.py` зависит |
| `services/parsers/ozon_realization.py:25` | XLSX-parser для realization — заглушка | Phase 1 | P1 — нужно для импорта старых отчётов |
| `workers/tasks/sync_communications.py:326` | History сообщений в чатах (только метаданные) | Phase 2.5 | P2 |
| `workers/tasks/maintenance.py:8` | Чистка sync_logs >90 дней, audit_logs в S3 | — | P2 — БД растёт |
| `services/forecasting/whatif.py:9` | Эластичность в whatif — наивно (сохранение объёма) | — | После AI Phase 1 (есть `elasticity` tool) |
| `workers/tasks/recompute_recommendations.py:168` | `longterm_seasonal_factor` подмешать из `seasonality.combined_seasonal_factor` | — | P2 — улучшит точность recs |
| `api/endpoints/plan_purchase.py:12` | `/progress` endpoint для факт vs план | — | P2 — UI завязан |

### 5. Заглушки `NotImplementedError`

- `services/forecasting/backlog.py:36` — `geography_index` — помечен «Phase 5 backlog» (норм)
- `services/forecasting/backlog.py:62` — `associated_conversions` — «Phase 5+ backlog» (норм)

Эти явно отложены и не вызываются в продакт-коде. **Не баг.**

---

## 🟢 Что хорошо

### Архитектура
- Единый `OzonSellerClient` с rate-limit + retry-backoff (`services/ozon_client.py`) — все sync-таски ходят через него.
- TimescaleDB hypertables правильно используются (transactions, ad_statistics, analytics_daily, market_trends_daily).
- Migration chain последовательная (0001→0029 без пропусков, ветвлений нет).

### Чистота недавних изменений (эта сессия)
- AI Phase 1: tools + orchestrator не дублируют логику, переиспользуют existing SQL (`forecasting.source_a` для прогноза, `placement_storage_daily` для хранения).
- Storage warning: один большой CTE-SQL, без N+1 (0.34 сек на 8 SKU).
- Seasonality detect оптимизирован тем же приёмом (раньше — таймаут).

### Документация
- `CLAUDE.md` в корне — точка правды для каждой Claude-сессии.
- `docs/transaction_list_v3_baseline.md` — фиксация структуры endpoint'а на 2026-06-03 (для P0 #12 — early-warning перед 6 июля).
- TZ-документы (`flowoi_master_brief.md`, `FLOWOI_AI_TZ.md`, `flowoi_tz_*.md`) → синхронизированы с реализацией.

---

## 🔍 Зоны не проверенные глубже

1. **Frontend dead components** — 52 страницы, не у всех есть роуты в `App.tsx`. Возможно есть осиротевшие.
2. **Unused indexes** — много `Index(...)` в моделях; нужен `pg_stat_user_indexes` на проде, чтобы выявить нулевые сканы.
3. **N+1 в API** — выборочно проверял, но не системно. Кандидаты: списочные endpoints со связями (orders/products/transactions).
4. **CSRF/XSS** — не аудитил, но FastAPI+JWT bearer-токен без cookies → CSRF не релевантен; XSS только если frontend инжектит untrusted-HTML, у нас всё через React (auto-escape).

---

## 📌 Чёткий список ToDo из аудита

| # | Файл:строки | Описание | Приоритет |
|---|---|---|---|
| A1 | `services/stock_query.py` (создать) | Вынести дубль `last_wh/last_agg/wh_sum/agg_sum` CTE из 5 мест в helper | P1 |
| A2 | `services/revenue_views.py` (создать) | Единый помощник `seller_revenue_for/buyer_revenue_for/ordered_value_for` | P1 |
| A3 | `services/reports.py:30,38,46` | Реализовать `/v1/report/finance/*` flow | P1 |
| A4 | `services/parsers/ozon_realization.py:25` | XLSX-parser realization | P1 |
| A5 | `workers/tasks/maintenance.py:8` | Чистка `sync_logs` >90 дней | P2 |
| A6 | `workers/tasks/recompute_recommendations.py:168` | `longterm_seasonal_factor` из seasonality | P2 |
| A7 | `api/endpoints/plan_purchase.py:12` | `/progress` факт vs план | P2 |

---

*Аудит сделан: 2026-06-03, после коммита `625f8d9`. Следующий аудит — после имплементации A1–A4 или через ~30 коммитов от текущего.*
