# Flowoi — пакет переноса проекта (handover)

Дата: 2026-06-01. Этот документ — самодостаточный контекст для продолжения работы в новом чате Claude. Скопируй целиком + короткий стартовый промт в конце.

---

## 1. Цель проекта

**Что:** Flowoi — SaaS-аналитика для продавцов маркетплейса Ozon. Веб-приложение «как Power BI, только для Ozon-селлеров», на flowoi.ru. (Кодовое имя в репо: `ozon-pro` / `ozonpro` — наследие, бренд только `Flowoi`.)

**Для кого:** соло-владельцы и команды продавцов на Ozon. Подключают свои кабинеты (Seller API + Performance API + Premium Plus/Pro), получают единую картину: дашборд, P&L, юнит-экономику, прогнозы закупок, воронку, маркеры, AI-чат.

**Конечный результат:** платный SaaS с тарифами под Ozon-тиры (free / premium / premium_plus / premium_pro). Конкуренты — nepsell.ru, sellematics, mpstats. Главная фишка — `Reverse-funnel` («задай цель → AI считает рецепт») + AI-чат с function calling.

**Этап:** Phase 1 + Phase 2 деплой 2026-05-28, Phase 3 (фичевый код) идёт. Production живой на flowoi.ru с реальными данными 3 активных кабинетов: `home`, `home pro`, `Stolz`. Все 119 трекерных задач закрыты на момент handover. ШАГ продукта — продолжать дотягивать функционал до полного MVP.

---

## 2. Главная идея и логика

**Общая концепция:** одно приложение, в которое продавец Ozon подключает свои кабинеты по API-ключам → автоматическая ежечасная синхронизация → готовые дашборды, P&L по магазину/товару/дню, прогнозы, воронка от показов до прибыли, AI-помощник.

**3 сквозных принципа (project_flowoi_principles):**
1. **Зеркало Ozon.** Что Ozon показывает в своём UI — мы повторяем точь-в-точь. Никаких «наших расчётов» которые расходятся с эталоном. Расхождение = баг.
2. **2 модели финансов.** `seller_revenue` (= `accruals_for_sale` — что Ozon начислил продавцу, с компенсацией СПП) vs `ordered_value` (= `Order.total_amount` = Σ `OrderItem.price × qty` — «Заказано» по **цене продавца**, до СПП). Эти ДВЕ цифры разные и обе важны. P&L и маржа считаются от `seller_revenue`. Что **физически заплатил покупатель** (после СПП) — это `customer_price` (per posting, из `/v2/posting/fbo/get`), отдельный витринный слой про спрос. ВАЖНО: `total_amount` — это цена ПРОДАВЦА, НЕ цена покупателя (подтверждено в `sync_orders._sum_amount`).
3. **Описание у каждой метрики.** В UI рядом с числом — источник и формула (api/xlsx/estimated/manual/missing).

**Ключевые сценарии уже отработаны:**
- Подключение кабинета → автосинк → дашборд оживает за час.
- Загрузка XLSX «Общие расходы» из Ozon UI → точная P&L per-SKU.
- Юнит-калькулятор: ввёл price/cost/comm_pct/spp_pct → прибыль на ед.
- WhatIf: бета-эластичности (имп → визиты, цена → заказы, реклама → имп) → сценарии «что если».
- Reverse-funnel: «хочу 5М ₽ выручки на этом SKU за 60 дней» → 3 сценария (трафик/реклама/цена) через bisection по WhatIf-движку.
- Кредиты вручную (Loans v1): тело в ДДС, % в P&L.
- Сверка с realization-отчётом Ozon: автокросс-чек прибыли по месяцу.

**Принятые решения:**
- **PostgreSQL 17 + TimescaleDB 2.20** на Selectel managed-DB (не AWS, не self-hosted).
- **FastAPI + async SQLAlchemy 2.0 + Celery + Redis** на backend; React 18 + Vite + Tailwind + zustand + react-query на фронте.
- **Bcrypt 4.0.1 закреплён** (passlib падает на новых).
- **ENCRYPTION_KEY менять НЕЛЬЗЯ** — иначе зашифрованные API-ключи Ozon в БД не расшифруются. Раз поставлен = навсегда.
- **Деплой через GitHub Actions / git pull на VPS** — никаких ручных правок в проде.
- **Идемпотентность через `ON CONFLICT DO UPDATE` ВЕЗДЕ** в celery-задачах.
- **`log.exception` без ключей в логах**.
- **«Не подставляй оценку молча»** — source-флаги обязательны (api / xlsx / estimated / manual / missing).
- **Тело займа НИКОГДА в P&L** — только % и комиссия.

**Что точно НЕ нужно:**
- Не угадывать поля Ozon API — проверять эмпирически (один запрос → посмотреть payload → потом писать парсер).
- НЕ полагаться на «лимит 90 дней» в /v2/posting/fbo/get — его нет (проверено).
- Не записывать оценки в primary колонки данных (затаптывает дневную динамику). Оценки — в отдельные таблицы / поля с source-флагом.
- НЕ пушить на main с `--no-verify`, не bypass-ить hooks.
- Не амендить уже опубликованные коммиты.
- Не делать `git add -A` или `git add .` без явной проверки untracked.
- Не двигать `delete + insert` без preserve-pattern для полей, которые заполняются отдельными тасками (например `customer_price` — было багом, мы пофиксили).

---

## 3. Уже сделано

### Структура репо
- `/backend` — FastAPI + Celery + alembic
- `/frontend` — Vite + React + TS
- `/docs` — markdown-доки (TZ, диагностика, handover)
- `compose.yml` — Docker Compose сервисы: `backend`, `worker` (Celery), `beat` (Celery beat), `frontend` (nginx), `nginx` (reverse proxy + TLS)
- `.github/workflows/test.yml` — CI на pytest

### Деплой
- VPS: Selectel, IP в `reference_ozon_pro_infra` memory. Docker Compose.
- Managed-DB: Selectel PostgreSQL 17 + TimescaleDB 2.20, прямой адрес в backend env, SSL обязателен.
- DNS / TLS / nginx: уже настроено, домен flowoi.ru.
- GitHub: `git@github.com:sasasamarin/ozon-pro.git`, main branch.
- Backups: `/root/backups/db_*.sql.gz` через Celery task раз в сутки + ручные снимки перед миграциями.

### Что подключено
- 3 кабинета Ozon (home, home pro, Stolz) с Seller API + Performance API ключами.
- Seller API: products, stocks (per-warehouse), prices, orders FBO+FBS, transactions, analytics_daily, ad_campaigns, ad_statistics, returns, cancellations, reviews, questions, realization (premium_plus), financing (как услуги Ozon, не настоящие кредиты).
- Performance API: campaigns, statistics с OAuth-токеном (срок жизни кеша в `OzonAccount.perf_token_expires_at`).
- Report API: `seller_placement_by_products` (storage per-day-per-warehouse-per-SKU), `seller_returns` (если есть).
- SMTP: Selectel mail, **порт 2525** (25/465/587 у Selectel заблокированы). Пароль в `.env` на VPS, НЕ в git.

### Что проверялось / решённые ошибки
1. **sync_orders делал `delete(OrderItem) + insert`** → стирал `customer_price` каждый час. Фикс: preserve-pattern (запоминаем customer_price перед delete, восстанавливаем после insert). Файл `backend/app/workers/tasks/sync_orders.py:340`.
2. **enrich_customer_price считался очень медленно** → распараллелено через `asyncio.gather + Semaphore(10)`, sleep 30s→5s. Файл `backend/app/workers/tasks/enrich_customer_price.py`.
3. **Storage в P&L дублировался через CASE-хак в ON CONFLICT** → переписано: `monthly_unit_economy.storage_from_xlsx` (точно из XLSX) + `placement_storage_daily(cabinet, sku, warehouse, day)` (raw API, PK по дню = дедуп). P&L через `COALESCE(xlsx, daily_sum)`. Миграция `0020_storage_split.py`.
4. **`/v2/finance/realization` payload читался неверно** (`r.get("sku")` вместо `r["item"]["sku"]`, `r.get("sale_qty")` вместо `r["delivery_commission"]["quantity"]`) → таблица realization_lines всегда оставалась пустой. Фикс в `sync_marketplace.py`: правильный парсинг + агрегация per-SKU взвешенно по qty.
5. **Customer_price 30-31 мая = 0%** → backfill через enrich + ФИКС preserve-pattern (см. п.1).
6. **Гипотеза «90-дневный лимит API»** оказалась ложной. Проверено эмпирически на постингах 2025-01-01 (16+ мес назад) — `/v2/posting/fbo/get` отдаёт всё. → Бэкфил всего хвоста, покрытие 98.6-100% за всю историю.
7. **6549 «оценочных» customer_price** записанных в `order_items.customer_price` через realization-derive → откачено NULL'ом, потому что усреднение по месяцу затаптывает дневные СПП-всплески. Оценка живёт в `customer_price_monthly_estimate` отдельной таблицей.
8. **«ozon_financing principal = тело долга»** — миф. На самом деле это агрегат уже удержанных услуг (early_payout + commission_installment). Настоящих кредитов Ozon в API нет. Реальные займы вводятся вручную через `/loans` (миграция `0021_loans.py`).
9. **bcrypt + passlib** — закреплены версии (`bcrypt==4.0.1`), на новых passlib падает.
10. **pre-commit fail при пуше** → правило: НЕ амендить, делать новый коммит после фикса.

---

## 4. Технический стек

**Frontend:**
- React 18 + Vite + TypeScript
- TailwindCSS (премиум-светлая тема, минимум серого)
- zustand (глобальный store: cabinets, filters)
- @tanstack/react-query (api-кэш)
- lucide-react (иконки)
- recharts (графики)
- nginx serve в production контейнере

**Backend:**
- Python 3.11
- FastAPI + uvicorn
- SQLAlchemy 2.0 (async) + asyncpg + psycopg2-binary (для alembic)
- Alembic (миграции)
- Pydantic v2
- passlib[bcrypt]==1.7.4 + bcrypt==4.0.1 (фиксированные)
- python-jose (JWT)
- cryptography (Fernet для шифрования Ozon-ключей)
- httpx + tenacity (внешние API)
- celery + redis + flower
- structlog + sentry-sdk
- aiosmtplib (SMTP отправка)
- openpyxl (XLSX-парсинг)

**База данных:**
- PostgreSQL 17 + TimescaleDB 2.20 (managed Selectel)
- 8 hypertables: `transactions`, `ad_statistics`, `account_balance_snapshots`, `market_competitor_prices`, `market_trends_daily`, `ozon_financing_movements`, `price_history`, `product_cost_history`, `sales_velocity_cache` (приблизительно; ряд из них может быть обычной таблицей пока)
- ~55 таблиц (после миграций 0019-0022 добавились: `monthly_unit_economy`, `placement_storage_daily`, `loans`, `loan_payments`, `customer_price_monthly_estimate`)

**Хостинг:**
- VPS: Selectel, Docker Compose (backend / worker / beat / frontend / nginx)
- Managed DB: Selectel PostgreSQL 17 + TimescaleDB
- Redis: внутри Compose
- DNS / TLS: уже настроены, домен flowoi.ru

**API (внешние):**
- Ozon Seller API (api-seller.ozon.ru): продукты, заказы, транзакции, отчёты, реализация, рассрочка-факторинг
- Ozon Performance API (api-performance.ozon.ru): OAuth + рекламные кампании + статистика
- SMTP: Selectel порт 2525

**Авторизация:**
- Email + password (passlib bcrypt)
- JWT access tokens (python-jose)
- Companies → Users → Members (team) → ozon_accounts
- API-ключи Ozon шифруются Fernet с `ENCRYPTION_KEY` (НЕ менять)

**Платежи:** пока нет (planned для тарифов free / premium / premium_plus / premium_pro).

**Внешние сервисы:**
- Sentry (sentry-sdk[fastapi]) для error tracking
- AWS S3 / aioboto3 (для будущих S3 ассетов, пока минимально)
- Render-прокси вне РФ (планируемый, для AI/LLM-проксирования — РФ → external LLM API)

**Переменные окружения (на VPS в `/home/ozonpro/app/.env` и docker compose env_file):**
```
# Database
DATABASE_URL=postgresql+asyncpg://ozonuser:[SECRET]@[DB_HOST]:[PORT]/ozonpro?ssl=require
DB_PASSWORD=[SECRET]

# Security
SECRET_KEY=[SECRET]              # JWT signing
ENCRYPTION_KEY=[SECRET]          # Fernet, НИКОГДА не меняй
JWT_ALGORITHM=HS256

# Redis / Celery
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# Sentry
SENTRY_DSN=[SECRET]

# SMTP (Selectel порт 2525)
SMTP_HOST=smtp.selcdn.ru
SMTP_PORT=2525
SMTP_USER=info@flowoi.ru
SMTP_PASSWORD=[SECRET]
SMTP_FROM=info@flowoi.ru

# Ozon-ключи кабинетов шифруются и хранятся в БД, не в env
```

---

## 5. Архитектура

### Поток данных

```
Ozon API (Seller + Performance + Report)
        │
        ▼
Celery sync-таски (ежечасно через beat schedule)
  ├─ sync_products
  ├─ sync_stocks
  ├─ sync_orders (FBO + FBS) + preserve customer_price
  ├─ sync_finance (transactions с разносом по статьям)
  ├─ sync_analytics_daily (impressions, sessions, ordered_units)
  ├─ sync_ads (campaigns + statistics)
  ├─ sync_marketplace (returns, cancellations, reviews, questions, REALIZATION помесячно)
  ├─ sync_placement_reports (storage per-day-warehouse-SKU)
  ├─ sync_financing (услуги Ozon: early_payout, commission_installment)
  ├─ enrich_customer_price (через /v2/posting/fbo/get для NULL'ов)
  ├─ reconcile_realization (раз в неделю, кросс-чек с XLSX)
  └─ backfill_customer_price_estimate (помесячный fallback из realization)
        │
        ▼
PostgreSQL + TimescaleDB
  ├─ companies, users, members (auth + multi-tenant)
  ├─ ozon_accounts (Seller + Perf API ключи зашифр.)
  ├─ products + price_history + product_cost_history
  ├─ stocks (snapshot + history)
  ├─ orders + order_items (с customer_price из enrich)
  ├─ transactions (hypertable, разнесено по статьям: sale_commission, acquiring, advertising, storage, last_mile, …)
  ├─ analytics_daily (per-day-per-product метрики: imp/cv/cart/orders/deliv)
  ├─ ad_campaigns + ad_statistics
  ├─ returns + cancellations
  ├─ reviews + questions (+ chat для коммуникаций)
  ├─ ozon_financing + ozon_financing_movements (услуги Ozon)
  ├─ loans + loan_payments (настоящие займы, ВРУЧНУЮ, не из API)
  ├─ monthly_unit_economy (XLSX «Общие расходы» юзера)
  ├─ placement_storage_daily (raw API из seller_placement_by_products)
  ├─ customer_price_monthly_estimate (fallback оценка для старых месяцев)
  ├─ sync_state (cursor'ы синков)
  ├─ markers + alert_rules + alerts_history + notifications
  ├─ email_log (отправка)
  └─ team + member_account_access (RBAC)
        │
        ▼
FastAPI endpoints (50+)
        │
        ▼
React + react-query
        │
        ▼
Пользователь
```

### Главные endpoints

```
# Auth + accounts
POST   /api/v1/auth/login, /register, /me, /refresh
GET    /api/v1/ozon-accounts/      — список кабинетов
POST   /api/v1/ozon-accounts/      — добавить (с шифрованием ключей)
PATCH  /api/v1/ozon-accounts/{id}  — обновить

# Дашборды
GET    /api/v1/dashboard/          — Phase 1 дашборд
GET    /api/v1/dashboard/v2        — Power-BI стиль

# Финансы
GET    /api/v1/finance/pnl         — декомпозиция P&L (с строкой «Проценты по кредитам» если loans>0)
GET    /api/v1/finance/cashflow    — ДДС с loan_inflow/outflow отдельно
GET    /api/v1/finance/transactions
GET    /api/v1/finance/expenses
GET    /api/v1/finance/account-balance
GET    /api/v1/finance/unit-economy
POST   /api/v1/finance/unit-economy/import — XLSX импорт «Общие расходы»

# Товары
GET    /api/v1/products/, /{id}, /economics, /calculator, /categories

# Заказы и возвраты
GET    /api/v1/orders/
GET    /api/v1/returns/

# Аналитика
GET    /api/v1/analytics/funnel + /v2
GET    /api/v1/analytics/summary
GET    /api/v1/analytics/heatmap
GET    /api/v1/analytics/stockouts + stockouts-by-region
GET    /api/v1/analytics/plan-vs-fact
GET    /api/v1/analytics/plan-purchase
GET    /api/v1/analytics/metrics-matrix
GET    /api/v1/analytics/day-explanation
POST   /api/v1/analytics/reverse-funnel/solve   ★ killer

# WhatIf
GET    /api/v1/whatif/betas/{product_id}
POST   /api/v1/whatif/simulate

# Кредиты
GET    /api/v1/credit/list                — услуги Ozon (НЕ кредиты)
GET    /api/v1/loans                      — настоящие займы (ручной ввод)
POST   /api/v1/loans                      — создать + автографик
GET    /api/v1/loans/{id}/payments
POST   /api/v1/loans/{id}/payments/{seq}/pay
POST   /api/v1/loans/{id}/payments        — ручной платёж
GET    /api/v1/loans/aggregate/period

# Закупки
GET    /api/v1/procurement/orders
GET    /api/v1/supply-params

# Коммуникации, маркеры, email, team — есть, см. routes.py
```

### Главные frontend страницы

```
/dashboard
/cabinets, /cabinets/new, /cabinets/:id
/products + /products/{id} + /products/economics + /products/calculator + /products/categories + /products/prices
/orders + /orders/fbo + /orders/fbs + /orders/returns
/finance/pnl + /finance/cashflow + /finance/transactions + /finance/expenses + /finance/balance + /finance/unit-economy/import + /finance/account-balance
/analytics/funnel + /analytics/reverse-funnel ★ + /analytics/summary + /analytics/heatmap + /analytics/stockouts + /analytics/metrics-matrix + /analytics/builder + /analytics/plan-vs-fact + /analytics/plan-purchase
/whatif
/credit       — Услуги ускоренного вывода Ozon (переименовано)
/loans        — настоящие кредиты (ручной ввод)
/markers + /alerts/settings + /alerts/history + /alerts/channels (часть placeholder)
/communications/reviews + /questions
/email + /email/templates
/team
/settings
```

---

## 6. Важные промты и инструкции

**Главный системный промт (как ведёт себя Claude в этом проекте):**

```
Ты ассистент-разработчик Flowoi (SaaS аналитика для Ozon-продавцов).

Стиль:
- Русский, на «ты», коротко.
- Без emoji в коде / комментариях / коммитах.
- Без markdown-табличек в чате если не запросили.
- Не повторяй то что юзер уже знает.

Технические инварианты:
- Деньги: Numeric(15,2), не float.
- Идемпотентность: ON CONFLICT DO UPDATE везде в celery-тасках.
- log.exception(...) без секретов в args.
- Шифрование ключей: Fernet с ENCRYPTION_KEY (не менять).
- Bcrypt 4.0.1 фиксирован.
- Тело займа НИКОГДА в P&L.
- customer_price = что заплатил покупатель; seller_price = что Ozon начислил продавцу. Не путать.

Источники данных (source-флаги обязательны):
- 'api' = из Seller/Performance/Report API в реальном времени
- 'xlsx' = из ручного XLSX-отчёта «Общие расходы»
- 'estimated' = pro-rata / interpolation / weighted-avg
- 'manual' = введено юзером
- 'missing' = нет данных, показывать «—», не 0

Не подставляй оценку молча в primary колонку. Оценка живёт в отдельной таблице/поле + UI «≈ оценка» с tooltip.

Авторизация действий:
- Обычная разработка — подряд без подтверждения.
- rm / DROP / миграция БД / прод-деплой / чистка таблиц — ВСЕГДА показывай и жди «ок».
- Не push --no-verify, не amend опубликованных коммитов.

Деплой:
- git commit → git push → ssh root@flowoi.ru → git pull → docker compose build → docker compose up -d --force-recreate → docker compose restart nginx.
- Backend авто-применяет alembic при старте.
- Managed-DB — единственный источник истины (не trust локальные .sql.gz dump).

Принципы продукта:
- Зеркало Ozon: что показывает Ozon UI — мы повторяем точно. Расхождение = баг.
- 2 модели финансов: seller_revenue (= accruals_for_sale) vs ordered_value (= Order.total_amount, цена продавца). Цена покупателя после СПП = customer_price.
- Описание у каждой метрики: рядом с числом — формула и источник.

Перед написанием парсера API:
- Дёрни 1 раз руками, посмотри РЕАЛЬНЫЙ payload, потом пиши. Не угадывай.
- Не предполагай лимиты («90 дней», «N запросов/мин») без эмпирической проверки.
```

**Промт для запуска reverse-funnel (UI-логика):**
```
Юзер выбирает: продукт + метрика цели (revenue/orders/net_profit/delivered) + значение + окно β.
Backend: compute_betas(product, days) → 3 сценария через solve_for_target() (bisection).
Если β.confidence == 'low' для рычага → возвращаем feasible=false + объяснение.
UI: 3 карточки (трафик / реклама / цена) с зелёным фоном (feasible) или жёлтым (недостижимо).
```

**Промт для AI-чата (planned, ещё не сделан):**
```
Function calling через GPT-4o-mini (или Claude через прокси, см. project_flowoi_ai_architecture).
Доступные функции: get_pnl, get_product_economics, get_funnel, get_loans_aggregate, etc.
LLM API key хранится в Render env (НЕ в РФ, НЕ в git).
```

---

## 7. Принятые продуктовые решения

**В MVP (есть на 2026-06-01):**
- Подключение кабинетов (Seller + Performance + Premium tier)
- 7 синков (products / stocks / orders / transactions / analytics / ads / marketplace)
- Дашборд v1 + v2 (Power BI стиль)
- P&L декомпозиция + cashflow + balance
- Юнит-калькулятор + WhatIf симулятор + Reverse-funnel
- Каталог товаров + per-product экономика + categories + tags
- Заказы FBO/FBS, возвраты, отмены
- Стокауты + регионы
- Воронка v2 (drill-down, Sankey, оверлей customer_price, scatter)
- Прогноз закупок (sales velocity + supply_params)
- Маркеры + history + правила
- Коммуникации (reviews + questions)
- Email-логи
- Внешние расходы + товарный баланс
- Кредиты Ozon (услуги) + Loans (настоящие, ручной ввод)
- Реализация-сверка
- Налоги (УСН Дох/Дох-Расх/ОСНО + НДС)
- Team + RBAC
- pytest + GitHub Actions CI

**Не в MVP (отложено):**
- AI-чат (function calling) — backbone есть (AIChat/AIMessage таблицы), front placeholder, нужна интеграция с external LLM через Render-прокси.
- Telegram-бот.
- Конкуренты (Premium Plus API уже есть, но front-страница placeholder).
- Платежи / биллинг тарифов.
- Wildberries (другой маркетплейс).
- Маркетинговые рассылки на покупателей.
- Рефинансирование кредитов.
- Календарь поставок.
- Качество поставщиков (брак-трекинг).
- Sezonality-страница (отдельная аналитика по году).

**Режимы работы:**
- Solo founder (один user, одна company, 3 кабинета) — текущий режим юзера.
- Team mode (CompanyMember + RBAC) — поддержан в схеме, не оттестирован вживую.
- Multi-tenant — все таблицы scoped по `company_id`, `user_id`, `cabinet_id`.

**Обязательно:**
- Идемпотентность синков.
- Source-флаги для прозрачности.
- Premium-tier guard в синках premium_plus / premium_pro.
- Бэкап перед каждой миграцией.
- Подтверждение для деструктивных операций.

**Можно позже:**
- Hypertables-миграции для legacy таблиц (transactions, stocks, analytics_daily).
- Token-bucket rate-limit per-account.
- Async-отчёты Performance API.
- Audit log более детальный.

**Решённые спорные моменты:**
- Тело займа НЕ в P&L (вариант 2 из ТЗ flowoi_tz_loans.md).
- Returns в P&L отдельной строкой (вариант 2, зеркало Ozon).
- Storage = COALESCE(XLSX, daily_API_sum) — XLSX побеждает.
- Customer_price оценка НЕ в primary колонку, отдельная estimate-таблица.
- Realization API подсасывает customer_price для проверки, но не как fallback в order_items.
- Reverse-funnel сейчас bisection по 1 рычагу (трафик / реклама / цена), не комбинация.

---

## 8. Текущие проблемы и незакрытые вопросы

**Не работает / частично:**
- Январь 2025 FBS-заказы (16 шт): `customer_price = NULL`, потому что enrich фильтрует `order_type='fbo'`. FBS-эквивалент `/v2/posting/fbs/get` не подключён.
- Reverse-funnel: для товаров с малой выборкой данных β.confidence='low' → все 3 сценария вернут «недостижимо», что норма, но юзеру может быть непонятно почему.
- Loans UI: график погашения как sparkline / столбиками — не визуализирован, только табличка.
- Storage_from_xlsx за май 2026: NULL, потому что юзер не перезагрузил XLSX (мы попросили). Daily-fallback покрывает корректно, но source='api_daily' вместо 'xlsx'.
- AI-чат, Telegram, конкуренты, рефинансирование, маркетинговые рассылки — placeholder.

**Где остановились:**
- Только что задеплоены Reverse-funnel + pytest+CI (коммит `d8f0cb7`).
- Все задачи в трекере closed. Нет «висящих» pending.
- Юзер запросил handover — этот документ.

**Первым делом проверить в новом чате:**
1. `git log --oneline -20` — что последние коммиты, синхронизирован ли локальный с remote.
2. `git status` — нет ли untracked файлов, не закоммиченных правок.
3. SSH доступ к flowoi.ru (если требуется деплой).
4. `docker compose ps` на VPS — все 5 контейнеров (backend / worker / beat / frontend / nginx) up.
5. `https://flowoi.ru` → 200 OK, `/login` доступен.
6. Backend health: `curl https://flowoi.ru/api/v1/system/health`.
7. Свежий alembic head: `docker exec ozon_backend alembic current` → должен быть `0022_customer_price_source`.

**Ошибки которые нельзя повторять:**
- Не пиши `delete + insert` в OrderItem без preserve customer_price (см. `sync_orders.py:340`).
- Не парси Ozon API «по аналогии» — проверь payload руками: `r["item"]["sku"]` ≠ `r.get("sku")`.
- Не записывай оценку в primary колонку (customer_price, storage и т.д.) без source-флага.
- Не предполагай «90-дневный лимит» в /v2/posting/fbo/get — его НЕТ.
- Не путай `seller_price` и `customer_price` (см. project-ozon-api-facts memory).
- Не амендь опубликованные коммиты после fail pre-commit hook.

**Места, требующие аккуратности:**
- Все целевые удержания в `transactions.services[]` — разнесены через `app/services/parsers/ozon_realization.py`. Если добавится новый Ozon-services type — он попадёт в `OperationOtherElectronicServices` пока не учтён явно.
- `ENCRYPTION_KEY` — глобальный синглтон, не менять. При компрометации — добавить миграцию ре-шифровки, не подменять ключ напрямую.
- Migrate-on-start: backend при `docker compose up` сам делает `alembic upgrade head`. Если миграция падает — backend не стартует, нужно править руками и пересобирать.
- `customer_price_monthly_estimate` теперь fallback — если когда-то Ozon API начнёт резать /posting/fbo/get >90д, можно вернуть бэкфил через realization.
- `loans` cascade удаление: при `DELETE FROM loans WHERE ...` каскадом удаляются `loan_payments`. Аккуратно с конкретными договорами в проде.

---

## 9. План следующих действий

**Шаг 1.** Проверить living state production (см. п.8 «Первым делом проверить»).

**Шаг 2.** Юзер обещал внести реальный займ через `/loans` UI → проверить что:
- `/finance/pnl` показывает строку «Проценты по кредитам» с суммой
- `/finance/cashflow` показывает «В т.ч. кредиты» блок
- `customer_price_source` НЕ зашёл в order_items как 'estimated_monthly' (мы откатили)

**Шаг 3.** Из p.7 «Не в MVP» — самое полезное по убыванию:
1. **AI-чат с function calling** (Phase 2 фундамент готов: AIChat/AIMessage таблицы, models, есть `project_flowoi_ai_architecture` memory с архитектурой Render-прокси). Нужен endpoint POST /api/v1/ai/chat + интеграция с OpenAI/Claude API через прокси + 5-10 function-call функций (get_pnl, get_economics, get_funnel, etc.) + front-page /ai-chat.
2. **Telegram-бот** — нужен webhook endpoint, привязка по one-time code, sender service. Низкоприоритетно если AI-чат не сделан.
3. **Конкуренты** (Premium Plus API уже есть): /products/competitors страница, отображение цен/остатков конкурентов, history по `market_competitor_prices`.
4. **Loans UI улучшения**: график погашения, диаграмма «остаток / процент» по времени.
5. **Hypertable-миграции** для legacy таблиц (transactions, stocks, analytics_daily) — данных нет ещё много, безопасно мигрировать.

**Шаг 4.** Технический долг:
- Расширить pytest: добавить тесты на customer_price preserve в sync_orders, на realization-парсер, на loan_schedule с граничными случаями (ставка > 100%? срок 600 мес?).
- Token-bucket per-account rate-limit для Seller + Performance API.
- Document `docs/API_REFERENCE.md` — список всех endpoint с примерами body/response.
- `.gitignore` clean (см. `project_phase_state` Phase 5 backlog п.2-3).

**Как проверить, что всё работает после деплоя:**
1. `https://flowoi.ru` → login.
2. /dashboard → данные за последние 7 дней не нулевые.
3. /products/economics → выбрать WandTech, увидеть avg_seller_price ≈ 10180, avg_customer_price ≈ 5424.
4. /analytics/reverse-funnel → WandTech, revenue=5000000, 60 дней → 3 сценария.
5. /loans → создать тестовый займ → проверить P&L строку «Проценты по кредитам».
6. `docker exec ozon_worker celery -A app.workers.celery_app inspect active` — должны быть beat schedule живы.
7. `tail /home/ozonpro/app/logs/*` — нет регулярных ERROR.

---

## 10. Инструкция для нового Claude-чата

### Как продолжать работу в новой ветке

**С чего начать:**
1. Прочитай этот документ целиком.
2. Прочитай auto-memory файлы (они подтянутся автоматически в системный промт): `user_ozon_pro`, `project_ozon_pro`, `project_flowoi_brand`, `project_phase_state`, `project_flowoi_principles`, `project_flowoi_ai_architecture`, `project_ozon_api_facts`, `feedback_style_ozon_pro`, `feedback_deploy_flowoi`, `feedback_authorization_flowoi`, `feedback_data_honesty`, `reference_ozon_pro_infra`.
3. Запусти `git log --oneline -20` чтобы увидеть свежие коммиты с момента handover (если их вообще будут к моменту чтения).
4. Спроси юзера что он хочет делать — не предлагай сам, дай выбрать.

**Какую роль взять Claude:**
- Старший разработчик-парный программист. Знаешь стек (FastAPI + async SQLAlchemy + React + Vite + Tailwind + Celery + Selectel + Docker Compose).
- Стиль: краткий русский, без воды, без emoji в коде. Деньги — Numeric(15,2). Source-флаги обязательны.
- Принимаешь решения по тех. рутине сам. Перед миграциями / DROP / rm / прод-деплоем — подтверждение.

**Какие файлы запросить первыми:**
1. `git log --oneline -20` (свежие изменения)
2. `backend/app/api/routes.py` (полный список endpoint)
3. `backend/app/models/__init__.py` (полный список моделей)
4. `backend/alembic/versions/` ls (последняя миграция)
5. `frontend/src/lib/menu.ts` (структура сайдбара)
6. `frontend/src/App.tsx` (роуты)
7. `docs/PROJECT_HANDOVER.md` (этот файл)

**Не задавать повторно (есть в handover):**
- Какой стек / hosting / DB.
- Какие кабинеты подключены (home, home pro, Stolz).
- Каков статус Ozon API (мифы про 90-дневный лимит развеяны).
- Что такое 2 модели финансов.
- Тело займа в P&L (нет).
- Кодовое имя `ozon-pro` vs бренд `Flowoi`.
- ENCRYPTION_KEY — не менять.
- Bcrypt 4.0.1 фиксированный.

**Что задавать (требует ввода):**
- LLM API key для AI-чата (нужен в Render env, не в git).
- Параметры реального займа когда юзер захочет ввести (сумма, ставка %, дата, срок).
- Какие external tools / interfaces / тарифы делать первыми.

**Если данных не хватает:**
- Проверь в `docs/` и `memory/` — есть ли уже ответ.
- Запусти `grep -rn "ключевое_слово" backend/ frontend/` (Bash) или Agent с subagent_type=Explore.
- Не угадывай Ozon API payload — дёрни эмпирически 1 раз (см. `tmp/probe_realization.py` как пример).
- Только если всё перечисленное не помогло — спроси юзера 1 коротким вопросом.

**Как проверять код и ошибки:**
- Перед каждым коммитом: `python3 -c "import ast; ast.parse(open('file.py').read())"` для каждого изменённого .py.
- TypeScript: `cd frontend && npx tsc --noEmit 2>&1 | grep error`.
- pytest: `docker exec -u root -w /app ozon_backend python -m pytest tests/`.
- API smoke: `curl -s -o /dev/null -w "%{http_code}\n" https://flowoi.ru/api/v1/<endpoint>` (ожидаем 401 если без auth — это норма).
- При ошибке: `docker logs ozon_backend --since 2m 2>&1 | grep -iE 'error|exception' | tail`.
- При фейле миграции: `docker exec ozon_backend alembic current` + `alembic history --verbose | head -20`.

**Как не тратить лишние токены:**
- Не читай повторно файлы, которые уже в контексте.
- Для широкого поиска используй Agent (Explore subagent_type), не grep вручную по 20 файлам.
- Не выводи длинные SQL результаты целиком — используй `LIMIT 10` или `head`.
- Длинные celery / docker logs — `grep -E pattern | tail -20`, не вся выдача.
- На «что есть в таблице X» — сначала `\d+ X` через psql, не SELECT *.
- Не запускай `sleep 600` — используй `until <check>; do sleep 10; done` или фоновое исполнение с notification.

**Безопасность (важно):**
- Никогда не выдавай содержимое `.env`, `ENCRYPTION_KEY`, SMTP-пароль, API-ключи кабинетов в чат. Если юзер просит секрет — отвечай «секрет в .env на VPS, я не могу его показать, могу подсказать как достать».
- Не суй credentials в коммиты (есть `.gitignore`, проверяй).
- При работе с базой через psql — используй `PGPASSWORD=$(grep DB_PASSWORD /etc/flowoi/backup.env | cut -d= -f2)` на VPS, не хардкодь пароль.

---

## Стартовый промт для нового чата

Скопируй это в начало нового чата:

```
Я продолжаю работу над Flowoi (codename ozon-pro) — SaaS аналитика для Ozon-продавцов.

Production живой на flowoi.ru, 3 кабинета, 119 задач закрыто, на момент handover открытых нет.

Прочитай docs/PROJECT_HANDOVER.md полностью — там цель проекта, стек, архитектура, что уже сделано, какие ошибки уже разбирали, текущий план и инструкции как работать.

Также подтянутся auto-memory файлы (проектные и feedback).

Не пиши общих приветствий, не пересказывай мне handover — я его уже читал. Жди моего запроса конкретной задачи.

Стиль: русский, на «ты», коротко, без emoji в коде/коммитах/комментариях. Деньги — Numeric(15,2). Source-флаги обязательны (api/xlsx/estimated/manual/missing). Тело займа НЕ в P&L. ENCRYPTION_KEY не менять.

Авторизация действий: обычная разработка подряд без подтверждения; rm / DROP / миграции БД / прод-деплой / чистка таблиц — всегда показывай и жди «ок».

Деплой: git push → ssh root@flowoi.ru → git pull → docker compose build → up -d --force-recreate → docker compose restart nginx.

Начни с `git log --oneline -20` чтобы увидеть свежее состояние.
```

---

**Документ написан 2026-06-01.** Последний коммит на момент написания: `d8f0cb7` (`fix(routes): добавить импорт reverse_funnel в API`).
