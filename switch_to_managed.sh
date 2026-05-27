#!/bin/bash
# Переключение backend на Selectel Managed TimescaleDB

set -e
echo "🚀 SWITCHING BACKEND TO MANAGED TIMESCALEDB"
echo "============================================"

APP_DIR=/home/ozonpro/app
ENV_FILE="$APP_DIR/.env"
BACKEND_ENV_FILE="$APP_DIR/backend/.env"

DB_HOST="45.157.160.36"
DB_PORT="5432"
DB_NAME="ozonpro"
DB_USER="ozonuser"
DB_PASS="hczwE5yQ23fk"

# Новый DATABASE_URL с SSL
NEW_DB_URL="postgresql+asyncpg://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}?ssl=require"
NEW_DB_URL_SYNC="postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}?sslmode=require"

cd "$APP_DIR"

# 1. Бэкап старого .env
echo "→ Backup current .env files..."
sudo -u ozonpro cp "$ENV_FILE" "${ENV_FILE}.docker-postgres.bak"
sudo -u ozonpro cp "$BACKEND_ENV_FILE" "${BACKEND_ENV_FILE}.docker-postgres.bak"

# 2. Обновляем .env в корне (для docker-compose)
echo "→ Updating .env files..."
sudo -u ozonpro python3 << PYEOF
import re
files = ['$ENV_FILE', '$BACKEND_ENV_FILE']
for fp in files:
    with open(fp, 'r') as f:
        content = f.read()
    # Заменим DATABASE_URL
    content = re.sub(
        r'^DATABASE_URL=.*$',
        f'DATABASE_URL=$NEW_DB_URL',
        content, flags=re.MULTILINE
    )
    content = re.sub(
        r'^DATABASE_URL_SYNC=.*$',
        f'DATABASE_URL_SYNC=$NEW_DB_URL_SYNC',
        content, flags=re.MULTILINE
    )
    # Обновим POSTGRES_* (если есть)
    for key, val in [('POSTGRES_USER', '$DB_USER'), ('POSTGRES_PASSWORD', '$DB_PASS'), ('POSTGRES_DB', '$DB_NAME')]:
        content = re.sub(
            f'^{key}=.*$',
            f'{key}={val}',
            content, flags=re.MULTILINE
        )
    with open(fp, 'w') as f:
        f.write(content)
    print(f'  ✓ Updated {fp}')
PYEOF

echo ""
echo "→ Current DATABASE_URL in backend/.env:"
sudo -u ozonpro grep "^DATABASE_URL" "$BACKEND_ENV_FILE" | sed 's/:[^@:]*@/:****@/g'

# 3. Перезапускаем backend
echo ""
echo "→ Restarting backend..."
sudo -u ozonpro docker compose restart backend
echo "✓ Backend restarted"

# 4. Ждём пока backend поднимется
echo ""
echo "→ Waiting for backend health..."
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 3
  HEALTH=$(curl -s http://localhost:8000/health/db 2>&1 || echo "fail")
  if echo "$HEALTH" | grep -q '"database":true'; then
    echo "✓ Backend healthy: $HEALTH"
    break
  fi
  echo "  Attempt $i: $HEALTH"
done

# 5. Применяем миграции на новой БД
echo ""
echo "→ Applying Alembic migrations to new DB..."
sudo -u ozonpro docker compose exec -T backend alembic upgrade head 2>&1 | head -20

# 6. Создаём hypertables
echo ""
echo "→ Initializing TimescaleDB hypertables..."
sudo -u ozonpro docker compose exec -T backend python -m app.scripts.init_hypertables 2>&1 | head -25

# 7. Финальная проверка
echo ""
echo "→ Final health check..."
curl -s http://localhost:8000/health
echo ""
curl -s http://localhost:8000/health/db
echo ""

echo ""
echo "============================================"
echo "✅ MIGRATION TO MANAGED DB DONE"
echo "============================================"
echo ""
echo "Подключение БД: $DB_HOST:$DB_PORT/$DB_NAME"
echo "Backup старого .env: ${ENV_FILE}.docker-postgres.bak"
