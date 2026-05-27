#!/bin/bash
# Миграция Ozon Pro на Selectel Managed TimescaleDB
# Запускается на VPS Marla
set -e

echo "🚀 MIGRATION TO MANAGED TIMESCALEDB"
echo "===================================="

APP_DIR=/home/ozonpro/app
DB_HOST="master.67b977ef-f1a3-47b0-b144-dea698f7bf0e.c.dbaas.selcloud.ru"
DB_PORT="5432"
DB_NAME="ozonpro"
DB_USER="ozonuser"
DB_PASS="hczwE5yQ23fk"

cd "$APP_DIR"

# 1. Скачать SSL сертификат
echo "→ Downloading Selectel CA cert..."
sudo -u ozonpro mkdir -p /home/ozonpro/.postgresql
sudo -u ozonpro wget -q https://storage.dbaas.selcloud.ru/CA.pem -O /home/ozonpro/.postgresql/root.crt
sudo -u ozonpro chmod 0600 /home/ozonpro/.postgresql/root.crt
echo "✓ SSL cert downloaded"

# 2. Проверить подключение
echo "→ Testing connection..."
PG_CONNECTION_OK=$(sudo -u ozonpro docker run --rm \
  --network app_ozon_net \
  -e PGPASSWORD="$DB_PASS" \
  -e PGSSLMODE=require \
  postgres:16-alpine \
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" 2>&1 || echo "FAILED")

if echo "$PG_CONNECTION_OK" | grep -q "FAILED"; then
  echo "⚠️  Direct connection failed via SSL. Trying without SSL..."
  PG_CONNECTION_OK=$(sudo -u ozonpro docker run --rm \
    --network app_ozon_net \
    -e PGPASSWORD="$DB_PASS" \
    postgres:16-alpine \
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" 2>&1)
  echo "$PG_CONNECTION_OK"
fi
echo "Connection test result:"
echo "$PG_CONNECTION_OK" | head -5
echo ""

# 3. Проверить TimescaleDB extension
echo "→ Checking TimescaleDB extension..."
TS_CHECK=$(sudo -u ozonpro docker run --rm \
  --network app_ozon_net \
  -e PGPASSWORD="$DB_PASS" \
  postgres:16-alpine \
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname LIKE '%timescale%';" 2>&1)
echo "$TS_CHECK"
echo ""

# 4. Если TimescaleDB не установлен — пытаемся создать
if ! echo "$TS_CHECK" | grep -qi "timescaledb"; then
  echo "→ TimescaleDB not installed, trying CREATE EXTENSION..."
  sudo -u ozonpro docker run --rm \
    --network app_ozon_net \
    -e PGPASSWORD="$DB_PASS" \
    postgres:16-alpine \
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    -c "CREATE EXTENSION IF NOT EXISTS timescaledb;" 2>&1 | head -10
  echo ""
fi

# 5. Список всех расширений
echo "→ All installed extensions:"
sudo -u ozonpro docker run --rm \
  --network app_ozon_net \
  -e PGPASSWORD="$DB_PASS" \
  postgres:16-alpine \
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
  -c "\dx" 2>&1 | head -30
echo ""

echo "===================================="
echo "DONE - check output above"
echo "===================================="
