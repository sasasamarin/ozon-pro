# Flowoi DB backup — установка на VPS

Стратегия: `pg_dump` запускается на **хосте** VPS (не в Docker-контейнере) через
`systemd` timer. Это убирает зависимость от пересборки backend-образа и работает
даже если Celery лежит.

## Файлы

| Файл                        | Куда на VPS                                | Назначение                       |
|-----------------------------|--------------------------------------------|----------------------------------|
| `backup_db.sh`              | `/usr/local/bin/flowoi-backup.sh`          | pg_dump + gzip + ротация         |
| `flowoi-backup.service`     | `/etc/systemd/system/flowoi-backup.service`| systemd service unit             |
| `flowoi-backup.timer`       | `/etc/systemd/system/flowoi-backup.timer`  | daily 04:00 UTC                  |
| `backup.env.example`        | `/etc/flowoi/backup.env` (с реальным паролем) | креды managed Postgres        |

## Первичная установка (выполняется один раз руками на VPS)

```bash
# 1. Поставить postgresql-client (если нет)
apt-get update && apt-get install -y postgresql-client

# 2. Подготовить директории
mkdir -p /root/backups/auto /etc/flowoi
chmod 700 /root/backups/auto /etc/flowoi

# 3. Скопировать конфиг и вписать реальный пароль из backend/.env
cp /root/ozon-pro/scripts/backup.env.example /etc/flowoi/backup.env
chmod 600 /etc/flowoi/backup.env
nano /etc/flowoi/backup.env   # заменить REPLACE_ME

# 4. Установить скрипт и systemd units
install -m 0755 /root/ozon-pro/scripts/backup_db.sh /usr/local/bin/flowoi-backup.sh
install -m 0644 /root/ozon-pro/scripts/flowoi-backup.service /etc/systemd/system/
install -m 0644 /root/ozon-pro/scripts/flowoi-backup.timer /etc/systemd/system/

# 5. Включить timer
systemctl daemon-reload
systemctl enable --now flowoi-backup.timer

# 6. Проверить расписание
systemctl list-timers flowoi-backup.timer
```

## Ручной снимок (перед правками формул)

```bash
/usr/local/bin/flowoi-backup.sh pre-formulas
# или
/usr/local/bin/flowoi-backup.sh manual
```

Файл появится в `/root/backups/auto/db_pre-formulas_<timestamp>.sql.gz`.

## Восстановление

```bash
# Положить дамп в безопасное место
gunzip < /root/backups/auto/db_pre-formulas_20260530_120000.sql.gz > /tmp/restore.sql

# Восстановить ВНИМАТЕЛЬНО — это перезапишет данные
PGPASSWORD=$(grep DB_PASSWORD /etc/flowoi/backup.env | cut -d= -f2) \
psql -h 45.157.160.36 -U ozonuser -d ozonpro -f /tmp/restore.sql
```

## Логи

```bash
# Последний прогон
journalctl -u flowoi-backup.service -n 50

# Что лежит сейчас
ls -lh /root/backups/auto/

# Следующий запуск timer
systemctl status flowoi-backup.timer
```

## Ротация

- последние **14 дневных** снимков
- по **1 снимку на ISO-неделю** (8 недель назад → 2 месяца истории)
- по **1 снимку на месяц** (6 месяцев истории)

Ручные снимки (`pre-formulas`, `manual`) попадают в окно «последние 14» как и
автоматические, потом обычно вытесняются. Если нужно сохранить ручной снимок
надолго — скопируй его в `/root/backups/keep/`, ротация туда не лезет.

## Восстановление — критические зависимости

**Прод-БД:** PostgreSQL 17.10 + TimescaleDB **2.20.0** (managed Selectel).

Дампы можно восстановить **только в Postgres 17 с TimescaleDB ≥ 2.20.0,
< следующая мажорная версия каталога**. Локальный dev-контейнер на PG 16 + TS 2.27.1
**не возьмёт** прод-дамп.

Проверенный образ для восстановления: `timescale/timescaledb:2.20.0-pg17`.

Процедура восстановления:
```sql
CREATE DATABASE restore_target;
\c restore_target
CREATE EXTENSION timescaledb;
SELECT timescaledb_pre_restore();
\i /path/to/dump.sql            -- или: gunzip -c file.sql.gz | psql ...
SELECT timescaledb_post_restore();
```

Без `pre_restore()` восстановятся таблицы, но фоновые джобы TimescaleDB начнут
лазить в пустые гипертаблицы во время накатывания → ошибки.

**Если Selectel обновит TimescaleDB на проде** (2.20 → 2.30+), старые дампы
могут перестать восстанавливаться без промежуточного апгрейда. Перед таким
обновлением — сделать тестовый restore на новой версии и проверить совместимость.

## S3 offsite backup (Selectel Object Storage)

`/root/backups/auto/` живёт только на VPS — если диск/VPS умрёт, backup умрёт
вместе. Поэтому подключена выгрузка в Selectel Object Storage (S3-совместимый).

Установка:
```bash
# 1. На VPS — поставить aws CLI
apt-get install -y awscli

# 2. Создать bucket «flowoi-backups» в Selectel + сервисного юзера с правами
#    на read/write/list ТОЛЬКО этого bucket'а. Подробно в s3.env.example.

# 3. Скопировать конфиг с реальными ключами
cp /home/ozonpro/app/scripts/s3.env.example /etc/flowoi/s3.env
chmod 600 /etc/flowoi/s3.env
nano /etc/flowoi/s3.env  # вписать S3_ACCESS_KEY, S3_SECRET_KEY

# 4. Установить s3-upload скрипт
install -m 0755 /home/ozonpro/app/scripts/backup_s3_upload.sh /usr/local/bin/flowoi-backup-s3.sh

# 5. Переустановить service unit (в нём уже прописан ExecStartPost для S3)
install -m 0644 /home/ozonpro/app/scripts/flowoi-backup.service /etc/systemd/system/
systemctl daemon-reload
```

Если `/etc/flowoi/s3.env` отсутствует, `backup_s3_upload.sh` выйдет с кодом 0 и
запишет warning в journal — основной backup продолжит работать локально.

## Что НЕ делаем сейчас (явно отложено)

- Шифрование архивов (GPG) — потенциальная PII (имена покупателей в
  `transactions.raw_response`) лежит в дампе открытым текстом. Шифровать
  перед S3 upload через `gpg --symmetric` с ключом из vault.
- Двухсторонняя репликация (logical replication к standby) — пока не нужно
  при объёме 15 МБ/дамп.
