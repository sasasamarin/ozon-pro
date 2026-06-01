# ТЗ: развести источники хранения (XLSX vs API), убрать CASE-костыль

**Контекст.** `monthly_unit_economy.storage` сейчас держит число из **двух источников** в одной ячейке:
- ручной XLSX «Общие расходы» — календарный месяц, точный, приоритетный;
- Report API `seller_placement_by_products` — скользящее 30-дн окно, периоды **перекрываются** (была выгрузка за 02.02–05.05).

CASE в `ON CONFLICT` это разруливает хрупко и **уже дал регрессию**: soluna03 storage −365 792 → −53 029 (API за 1–5 мая затёр ручной полный май). Достаточно одной перезагрузки или второго кабинета — и снова перетрётся. Плюс не видно, что в ячейке: точное число или API-затычка.

## Корень (три проблемы, одно решение)
1. Два источника воюют за одну ячейку.
2. API-окна перекрываются → риск **двойного счёта** в годовом/квартальном P&L.
3. API-отчёт — per-day-per-SKU-per-warehouse → на (SKU, месяц) много строк; суммировать надо без потери складов и без двойного счёта дней.

**Решение:** сырой API писать в отдельную **daily-таблицу с естественным ключом** (день дедуплицируется сам через PK), в `monthly` держать только XLSX. P&L берёт XLSX, а где его нет — сумму из daily. CASE исчезает, регрессия становится физически невозможной.

## Миграция (бэкап ПЕРЕД любым ALTER)
1. `pg_dump -t monthly_unit_economy ... -Fc` в бэкап.
2. `ALTER TABLE monthly_unit_economy ADD COLUMN storage_from_xlsx NUMERIC(14,4);`
3. Backfill из того, что уже точное:
   ```sql
   UPDATE monthly_unit_economy
   SET storage_from_xlsx = storage
   WHERE source_file IS NOT NULL
     AND source_file NOT LIKE 'REPORT_%';   -- т.е. пришло из ручного XLSX
   ```
   API-строки (`source_file LIKE 'REPORT_%'`) в `storage` не трогаем — их заменит daily-таблица + перезагрузка XLSX.
4. Новая таблица сырого хранения из API:
   ```sql
   CREATE TABLE IF NOT EXISTS placement_storage_daily (
     cabinet_id   BIGINT NOT NULL,
     sku          BIGINT NOT NULL,
     warehouse    TEXT   NOT NULL,
     day          DATE   NOT NULL,
     storage_cost NUMERIC(14,4) NOT NULL,
     source_report TEXT,
     imported_at  TIMESTAMPTZ DEFAULT now(),
     PRIMARY KEY (cabinet_id, sku, warehouse, day)
   );
   ```
   PK `(cabinet_id, sku, warehouse, day)` → перекрывающиеся отчёты делают UPSERT в **тот же день**, двойного счёта нет.

## Код
- **`sync_placement_reports` / `placement_report_parser`:** писать НЕ в `monthly_unit_economy.storage`, а в `placement_storage_daily` (`INSERT … ON CONFLICT (cabinet_id,sku,warehouse,day) DO UPDATE SET storage_cost = EXCLUDED.storage_cost`). Убрать запись `storage` в monthly и **весь CASE-хак**.
- **XLSX-импортёр:** `storage` из файла → `storage_from_xlsx` (а не в `storage`).
- **P&L / Economics — эффективное хранение по месяцу:**
  ```sql
  COALESCE(
    m.storage_from_xlsx,
    (SELECT SUM(d.storage_cost) FROM placement_storage_daily d
      WHERE d.cabinet_id = m.cabinet_id AND d.sku = m.sku
        AND d.day >= m.month AND d.day < (m.month + INTERVAL '1 month'))
  )
  ```
  XLSX приоритет — явно, через COALESCE, а не через хрупкий CASE.
- **Годовой/квартальный P&L:** хранение суммировать по месяцам через эту же функцию. Так как daily уже дедуплицирован по дню, наложение 30-дн окон исключено.
- **UI:** подписать источник у ячейки хранения — «точно (отчёт за месяц)» если из XLSX, «оценка (API)» если из daily (твой принцип «откуда цифра»).

## Старая колонка
`storage` **не дропать** в этой миграции — оставить, P&L на неё больше не смотрит. Дроп — отдельным шагом после проверки на проде.

## Действие юзера после деплоя
Перезагрузить XLSX «Общие расходы» за май через `/finance/unit-economy/import` → заполнит `storage_from_xlsx = −365 792` для soluna03. С этого момента источник = имя файла, автосинк его не трогает (он пишет только в daily).

## Приёмка (на майских данных этого кабинета)
- soluna03: `storage_from_xlsx = −365 792` (после перезагрузки XLSX).
- `placement_storage_daily`, soluna03, дни 01–05.05: `SUM(storage_cost) ≈ −53 029`.
- P&L soluna03 за май использует **−365 792** (XLSX победил в COALESCE), не −53 029.
- Идемпотентность overlap: импортировать один и тот же API-отчёт дважды → SUM в daily **не меняется**.
- Контроль из прошлого ТЗ не сломан: прибыль до с/с по магазину за май = **1 993 714 ₽**.

## Принципы
Маленькими шагами; бэкап перед миграцией; после каждого шага — сверка 1:1 с кабинетом. Сначала показать **план** (какие файлы тронешь, зависимости, что может сломаться), потом код. Движок общий по всем кабинетам — `cabinet_id` везде в ключах и фильтрах.
