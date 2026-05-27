#!/bin/bash
# Проверка состояния managed БД
DB_HOST="45.157.160.36"
DB_PASS="hczwE5yQ23fk"

echo "=== Tables in ozonpro DB ==="
sudo -u ozonpro docker run --rm \
  -e PGPASSWORD="$DB_PASS" \
  postgres:16-alpine \
  psql "host=$DB_HOST port=5432 user=ozonuser dbname=ozonpro sslmode=require" \
  -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;" 2>&1

echo ""
echo "=== TimescaleDB hypertables ==="
sudo -u ozonpro docker run --rm \
  -e PGPASSWORD="$DB_PASS" \
  postgres:16-alpine \
  psql "host=$DB_HOST port=5432 user=ozonuser dbname=ozonpro sslmode=require" \
  -c "SELECT hypertable_name FROM timescaledb_information.hypertables;" 2>&1

echo ""
echo "=== Backend Health ==="
echo -n "  /health:    "; curl -s http://localhost:8000/health
echo ""
echo -n "  /health/db: "; curl -s http://localhost:8000/health/db
echo ""

echo ""
echo "=== Docker Containers ==="
sudo -u ozonpro docker compose ps --format "table {{.Service}}\t{{.State}}\t{{.Status}}"

echo ""
echo "✅ Check done"
