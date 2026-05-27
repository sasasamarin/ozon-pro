#!/bin/bash
# Полный аудит MVP Ozon Pro

echo ""
echo "███████████████████████████████████████████████████████"
echo "█  OZON PRO MVP — FULL AUDIT REPORT                  █"
echo "███████████████████████████████████████████████████████"
echo ""

cd /home/ozonpro/app

# ============================================
# 1. КОНТЕЙНЕРЫ И СЕРВИСЫ
# ============================================
echo "━━━ 1. DOCKER CONTAINERS ━━━"
sudo -u ozonpro docker compose ps
echo ""

# ============================================
# 2. БАЗА ДАННЫХ
# ============================================
echo "━━━ 2. DATABASE (Managed TimescaleDB) ━━━"
DB_PASS="hczwE5yQ23fk"
DB_CONN="host=45.157.160.36 port=5432 user=ozonuser dbname=ozonpro sslmode=require"

echo "→ Tables count:"
sudo -u ozonpro docker run --rm -e PGPASSWORD="$DB_PASS" postgres:16-alpine \
  psql "$DB_CONN" -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"

echo "→ Hypertables:"
sudo -u ozonpro docker run --rm -e PGPASSWORD="$DB_PASS" postgres:16-alpine \
  psql "$DB_CONN" -c "SELECT hypertable_name FROM timescaledb_information.hypertables;"

echo "→ Users registered:"
sudo -u ozonpro docker run --rm -e PGPASSWORD="$DB_PASS" postgres:16-alpine \
  psql "$DB_CONN" -c "SELECT email, full_name, created_at FROM users;"

echo "→ Companies:"
sudo -u ozonpro docker run --rm -e PGPASSWORD="$DB_PASS" postgres:16-alpine \
  psql "$DB_CONN" -c "SELECT name, subscription_tier, is_active FROM companies;"

echo "→ Database size:"
sudo -u ozonpro docker run --rm -e PGPASSWORD="$DB_PASS" postgres:16-alpine \
  psql "$DB_CONN" -c "SELECT pg_size_pretty(pg_database_size('ozonpro')) AS size;"

echo ""

# ============================================
# 3. ВСЕ API ENDPOINTS
# ============================================
echo "━━━ 3. API ENDPOINTS ━━━"
echo "→ /health:"
curl -s http://localhost:8000/health
echo ""
echo "→ /health/db:"
curl -s http://localhost:8000/health/db
echo ""
echo "→ OpenAPI docs:"
curl -s http://localhost:8000/openapi.json | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f'{m.upper()} {p}') for p,ops in d['paths'].items() for m in ops if m in ['get','post','put','delete','patch']]" 2>/dev/null | sort
echo ""

# ============================================
# 4. BACKEND ОШИБКИ (последние 30 строк ERROR)
# ============================================
echo "━━━ 4. BACKEND ERRORS (last 24h) ━━━"
sudo -u ozonpro docker compose logs backend --tail=200 2>&1 | grep -iE "error|exception|traceback|failed" | grep -v "INFO" | tail -20
echo ""

# ============================================
# 5. BEAT И NGINX (которые рестартуют)
# ============================================
echo "━━━ 5. BEAT logs ━━━"
sudo -u ozonpro docker compose logs beat --tail=15 2>&1 | tail -15
echo ""
echo "━━━ 6. NGINX logs ━━━"
sudo -u ozonpro docker compose logs nginx --tail=15 2>&1 | tail -15
echo ""

# ============================================
# 7. WORKER (Celery)
# ============================================
echo "━━━ 7. WORKER (Celery) ━━━"
sudo -u ozonpro docker compose logs worker --tail=10 2>&1 | tail -10
echo ""

# ============================================
# 8. SYSTEM RESOURCES
# ============================================
echo "━━━ 8. SYSTEM RESOURCES ━━━"
echo "→ Disk usage:"
df -h / /home 2>/dev/null | grep -v tmpfs
echo ""
echo "→ Memory:"
free -h
echo ""
echo "→ Load avg:"
uptime
echo ""

# ============================================
# 9. DOCKER STATS
# ============================================
echo "━━━ 9. DOCKER STATS (one snapshot) ━━━"
sudo -u ozonpro docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"
echo ""

# ============================================
# 10. ENV CHECK
# ============================================
echo "━━━ 10. ENV CHECK (sensitive masked) ━━━"
sudo -u ozonpro grep -E "^[A-Z_]+=" /home/ozonpro/app/backend/.env 2>/dev/null | sed -E 's/=.*PASSWORD.*$/=[MASKED]/; s/(KEY|SECRET|TOKEN)=.*/\1=[MASKED]/; s/(:[^@]*)@/:[MASKED]@/g' | head -30
echo ""

# ============================================
# 11. ALEMBIC STATUS
# ============================================
echo "━━━ 11. ALEMBIC MIGRATION STATUS ━━━"
sudo -u ozonpro docker compose exec -T backend alembic current 2>&1 | tail -5
echo ""

# ============================================
# 12. ALL TABLES SIZES
# ============================================
echo "━━━ 12. TABLES SIZES ━━━"
sudo -u ozonpro docker run --rm -e PGPASSWORD="$DB_PASS" postgres:16-alpine \
  psql "$DB_CONN" -c "SELECT schemaname, relname AS table_name, pg_size_pretty(pg_total_relation_size(relid)) AS size FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 20;"
echo ""

echo "███████████████████████████████████████████████████████"
echo "█  AUDIT COMPLETE                                    █"
echo "███████████████████████████████████████████████████████"
