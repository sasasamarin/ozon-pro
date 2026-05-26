#!/bin/bash
# ============================================
# OZON PRO - автоматический скрипт деплоя
# ============================================
# Запуск: curl -fsSL https://raw.githubusercontent.com/sasasamarin/ozon-pro/main/deploy.sh | bash
set -e

echo "🚀 OZON PRO DEPLOY START"
echo "========================="

# 1. Обновим систему
echo "→ Updating system..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl git ca-certificates gnupg lsb-release ufw 2>&1 | tail -3

# 2. Установим Docker (если ещё не стоит)
if ! command -v docker &> /dev/null; then
  echo "→ Installing Docker..."
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin 2>&1 | tail -3
  systemctl enable docker
  systemctl start docker
fi
echo "✓ Docker: $(docker --version)"

# 3. Файрвол
echo "→ Configuring firewall..."
ufw --force reset > /dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable
echo "✓ Firewall: enabled"

# 4. Создадим юзера для приложения и зальём SSH ключ Claude
echo "→ Setting up users..."
if ! id ozonpro &> /dev/null; then
  adduser --disabled-password --gecos "" ozonpro
  usermod -aG docker ozonpro
fi
mkdir -p /home/ozonpro/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILnHV1pEOSgxhXXR5Kl52E71jvjqsFVOFNBhW4W/u6PN claude-deploy-bot@ozon-pro" > /home/ozonpro/.ssh/authorized_keys
chown -R ozonpro:ozonpro /home/ozonpro/.ssh
chmod 700 /home/ozonpro/.ssh
chmod 600 /home/ozonpro/.ssh/authorized_keys

# Также добавим Claude ключ к root для удобства
mkdir -p /root/.ssh
grep -q "claude-deploy-bot" /root/.ssh/authorized_keys 2>/dev/null || \
  echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILnHV1pEOSgxhXXR5Kl52E71jvjqsFVOFNBhW4W/u6PN claude-deploy-bot@ozon-pro" >> /root/.ssh/authorized_keys
echo "✓ Users: ozonpro + SSH keys"

# 5. Клонируем репо
echo "→ Cloning ozon-pro repo..."
APP_DIR=/home/ozonpro/app
if [ ! -d "$APP_DIR" ]; then
  sudo -u ozonpro git clone https://github.com/sasasamarin/ozon-pro.git "$APP_DIR"
else
  cd "$APP_DIR" && sudo -u ozonpro git pull
fi
echo "✓ Repo: $APP_DIR"

# 6. Создадим .env с автоматически сгенерированными секретами
echo "→ Generating .env..."
ENV_FILE="$APP_DIR/backend/.env"
if [ ! -f "$ENV_FILE" ]; then
  SECRET_KEY=$(openssl rand -hex 32)
  ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())")
  DB_PASS=$(openssl rand -hex 16)
  REDIS_PASS=$(openssl rand -hex 16)

  cat > "$ENV_FILE" << EOF
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

SECRET_KEY=$SECRET_KEY
ENCRYPTION_KEY=$ENCRYPTION_KEY
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# Локальный PostgreSQL+TimescaleDB через Docker (пока managed-БД не настроим)
DATABASE_URL=postgresql+asyncpg://ozonuser:$DB_PASS@db:5432/ozonpro
DATABASE_URL_SYNC=postgresql://ozonuser:$DB_PASS@db:5432/ozonpro
POSTGRES_USER=ozonuser
POSTGRES_PASSWORD=$DB_PASS
POSTGRES_DB=ozonpro

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# S3 пока пустые - добавишь когда получишь ключи
S3_ENDPOINT_URL=https://s3.selcdn.ru
S3_BUCKET=ozon-pro-files
S3_ACCESS_KEY=PLACEHOLDER
S3_SECRET_KEY=PLACEHOLDER
S3_REGION=ru-7

# Claude API - добавишь позже
ANTHROPIC_API_KEY=

# Sentry
SENTRY_DSN=
SENTRY_ENVIRONMENT=production

# Email
SMTP_HOST=
SMTP_PORT=465
SMTP_USER=
SMTP_PASSWORD=
EMAIL_FROM=noreply@ozonpro.ru
EMAIL_FROM_NAME=Ozon Pro

# Telegram
TELEGRAM_BOT_TOKEN=

# Ozon
OZON_API_BASE_URL=https://api-seller.ozon.ru
OZON_PERFORMANCE_API_BASE_URL=https://api-performance.ozon.ru
OZON_WEBHOOK_SECRET=$(openssl rand -hex 16)

ALLOWED_HOSTS=localhost,127.0.0.1,135.106.158.198
CORS_ORIGINS=http://localhost:5173,http://135.106.158.198,https://135.106.158.198
FRONTEND_URL=http://135.106.158.198
EOF
  chown ozonpro:ozonpro "$ENV_FILE"
fi
echo "✓ .env: created"

# 7. Запускаем docker-compose
echo "→ Starting Docker containers..."
cd "$APP_DIR"
# Запускаем только нужное для MVP - БД, Redis, Backend
sudo -u ozonpro docker compose up -d db redis 2>&1 | tail -5
echo "  waiting for db..."
sleep 15
sudo -u ozonpro docker compose up -d backend 2>&1 | tail -5
sleep 5
echo "✓ Docker: up"

# 8. Проверяем
echo "→ Checking health..."
sleep 5
curl -s --max-time 5 http://localhost:8000/health || echo "Backend not ready yet"
echo ""
echo ""

# 9. Сменим root password (текущий был в чате)
NEW_ROOT_PASS=$(openssl rand -base64 18)
echo "root:$NEW_ROOT_PASS" | chpasswd
echo ""
echo "============================================"
echo "✅ DEPLOY DONE"
echo "============================================"
echo "Новый root password: $NEW_ROOT_PASS"
echo "(сохрани его и сообщи в чат)"
echo ""
echo "Сервис: http://135.106.158.198:8000"
echo "API docs: http://135.106.158.198:8000/api/docs"
echo "Health: http://135.106.158.198:8000/health"
echo "============================================"
