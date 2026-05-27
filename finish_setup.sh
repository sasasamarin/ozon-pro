#!/bin/bash
# Финальная настройка MVP Ozon Pro
# Применяет миграции на новой managed БД, создаёт hypertables, регистрирует юзера

echo "🚀 FINISHING OZON PRO MVP SETUP"
echo "================================"
cd /home/ozonpro/app

DB_HOST="45.157.160.36"
DB_PASS="hczwE5yQ23fk"

# 1. Сбросить alembic state (на случай если стоит head, но таблиц нет)
echo ""
echo "→ Step 1: Reset alembic_version..."
sudo -u ozonpro docker compose exec -T backend alembic stamp base 2>&1 | tail -3

# 2. Применить миграции 
echo ""
echo "→ Step 2: Apply migrations (creating tables)..."
sudo -u ozonpro docker compose exec -T backend alembic upgrade head 2>&1 | tail -20

# 3. Создать TimescaleDB hypertables
echo ""
echo "→ Step 3: Create TimescaleDB hypertables..."
sudo -u ozonpro docker compose exec -T backend python -m app.scripts.init_hypertables 2>&1 | head -25

# 4. Проверка таблиц
echo ""
echo "→ Step 4: Verify tables in new DB..."
sudo -u ozonpro docker run --rm \
  -e PGPASSWORD="$DB_PASS" \
  postgres:16-alpine \
  psql "host=$DB_HOST port=5432 user=ozonuser dbname=ozonpro sslmode=require" \
  -c "SELECT count(*) AS tables_count FROM information_schema.tables WHERE table_schema='public';" 2>&1

# 5. Hypertables
echo ""
echo "→ Step 5: Verify hypertables..."
sudo -u ozonpro docker run --rm \
  -e PGPASSWORD="$DB_PASS" \
  postgres:16-alpine \
  psql "host=$DB_HOST port=5432 user=ozonuser dbname=ozonpro sslmode=require" \
  -c "SELECT hypertable_name FROM timescaledb_information.hypertables;" 2>&1

# 6. Регистрация первого юзера
echo ""
echo "→ Step 6: Register first user..."
cat > /tmp/reg_user.json << JSONEOF
{
  "email": "sasasamarin@gmail.com",
  "password": "OzonPro2026Strong",
  "full_name": "Alex Samarin",
  "company_name": "STOLZ KRAFT"
}
JSONEOF

RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d @/tmp/reg_user.json)
echo "Response: $RESPONSE" | head -3

# 7. Финальная проверка
echo ""
echo "→ Step 7: Final health check..."
echo "  /health:    $(curl -s http://localhost:8000/health)"
echo "  /health/db: $(curl -s http://localhost:8000/health/db)"

# 8. Контейнеры
echo ""
echo "→ Step 8: Docker containers status..."
sudo -u ozonpro docker compose ps --format "table {{.Service}}\t{{.State}}\t{{.Status}}"

rm -f /tmp/reg_user.json

echo ""
echo "================================"
echo "✅ SETUP DONE"
echo "================================"
