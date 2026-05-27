#!/bin/bash
# Миграция Ozon Pro на Selectel Managed TimescaleDB (через публичный IP)

echo "🚀 MIGRATION TO MANAGED TIMESCALEDB"
echo "===================================="

APP_DIR=/home/ozonpro/app
DB_HOST="45.157.160.36"
DB_PORT="5432"
DB_NAME="ozonpro"
DB_USER="ozonuser"
DB_PASS="hczwE5yQ23fk"

cd "$APP_DIR"

# 1. Скачать SSL сертификат Selectel CA
echo "→ Downloading Selectel CA cert..."
sudo -u ozonpro mkdir -p /home/ozonpro/app/certs
sudo -u ozonpro wget -q https://storage.dbaas.selcloud.ru/CA.pem -O /home/ozonpro/app/certs/selectel-ca.pem
sudo -u ozonpro chmod 0600 /home/ozonpro/app/certs/selectel-ca.pem
echo "✓ SSL cert downloaded ($(wc -c < /home/ozonpro/app/certs/selectel-ca.pem) bytes)"

# 2. Тест подключения через psql БЕЗ SSL
echo ""
echo "→ Test 1: Connection WITHOUT SSL..."
sudo -u ozonpro docker run --rm \
  -e PGPASSWORD="$DB_PASS" \
  postgres:16-alpine \
  psql "host=$DB_HOST port=$DB_PORT user=$DB_USER dbname=$DB_NAME sslmode=disable" \
  -c "SELECT version();" 2>&1 | head -5

# 3. Тест подключения с SSL (verify-ca)
echo ""
echo "→ Test 2: Connection WITH SSL (require)..."
sudo -u ozonpro docker run --rm \
  -e PGPASSWORD="$DB_PASS" \
  postgres:16-alpine \
  psql "host=$DB_HOST port=$DB_PORT user=$DB_USER dbname=$DB_NAME sslmode=require" \
  -c "SELECT version();" 2>&1 | head -5

# 4. Список расширений
echo ""
echo "→ Listing extensions in ozonpro DB..."
sudo -u ozonpro docker run --rm \
  -e PGPASSWORD="$DB_PASS" \
  postgres:16-alpine \
  psql "host=$DB_HOST port=$DB_PORT user=$DB_USER dbname=$DB_NAME sslmode=require" \
  -c "\dx" 2>&1 | head -25

# 5. Попытка создать TimescaleDB extension
echo ""
echo "→ Trying CREATE EXTENSION timescaledb..."
sudo -u ozonpro docker run --rm \
  -e PGPASSWORD="$DB_PASS" \
  postgres:16-alpine \
  psql "host=$DB_HOST port=$DB_PORT user=$DB_USER dbname=$DB_NAME sslmode=require" \
  -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;" 2>&1 | head -10

echo ""
echo "→ Final extensions list:"
sudo -u ozonpro docker run --rm \
  -e PGPASSWORD="$DB_PASS" \
  postgres:16-alpine \
  psql "host=$DB_HOST port=$DB_PORT user=$DB_USER dbname=$DB_NAME sslmode=require" \
  -c "SELECT extname, extversion FROM pg_extension;" 2>&1 | head -15

echo ""
echo "===================================="
echo "DIAGNOSTICS DONE"
echo "===================================="
