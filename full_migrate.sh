#!/bin/bash
# Полная миграция БД: сбросить alembic state, применить миграции, создать hypertables, проверить

echo "🚀 FULL DB MIGRATION"
echo "===================="
cd /home/ozonpro/app

echo "→ Step 1: Reset alembic_version (stamp base)..."
sudo -u ozonpro docker compose exec -T backend alembic stamp base 2>&1 | tail -5

echo ""
echo "→ Step 2: Apply ALL migrations (upgrade head)..."
sudo -u ozonpro docker compose exec -T backend alembic upgrade head 2>&1 | tail -20

echo ""
echo "→ Step 3: Initialize TimescaleDB hypertables..."
sudo -u ozonpro docker compose exec -T backend python -m app.scripts.init_hypertables 2>&1 | head -30

echo ""
echo "→ Step 4: Check tables..."
DB_PASS="hczwE5yQ23fk"
sudo -u ozonpro docker run --rm \
  -e PGPASSWORD="$DB_PASS" \
  postgres:16-alpine \
  psql "host=45.157.160.36 port=5432 user=ozonuser dbname=ozonpro sslmode=require" \
  -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;" 2>&1

echo ""
echo "→ Step 5: TimescaleDB hypertables..."
sudo -u ozonpro docker run --rm \
  -e PGPASSWORD="$DB_PASS" \
  postgres:16-alpine \
  psql "host=45.157.160.36 port=5432 user=ozonuser dbname=ozonpro sslmode=require" \
  -c "SELECT hypertable_name FROM timescaledb_information.hypertables;" 2>&1

echo ""
echo "→ Step 6: Backend health..."
curl -s http://localhost:8000/health/db
echo ""

echo ""
echo "✅ Migration complete"
