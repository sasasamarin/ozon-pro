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

## Что НЕ делаем сейчас (явно отложено)

- S3/Selectel Object Storage — `/root/backups/auto/` живёт только на VPS;
  если диск умрёт, backup умрёт вместе. Следующий шаг — синк в Selectel S3.
- Шифрование архивов (GPG) — потенциальная PII (имена покупателей в
  `transactions.raw_response`) лежит в дампе открытым текстом.
