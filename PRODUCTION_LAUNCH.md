# Production launch checklist для flowoi.ru

## 1. ⚠️ КРИТИЧНО: Закрыть managed-БД (БЛОКЕР)

Сейчас Selectel managed-БД доступна **с любого IP** (`0.0.0.0/0`).
В production должна быть открыта **только для VPS** (`135.106.158.198/32`).

### Где сделать:

```
Selectel панель
  → Облачные базы данных (Managed Databases)
  → ozonpro (или какое имя у тебя)
  → вкладка «Безопасность» / «Сетевой доступ» / «Firewall»
  → правила доступа
```

### Что сделать:

1. Найти текущее правило `0.0.0.0/0` (открыто всем)
2. **Удалить** его
3. **Добавить** новое правило: `135.106.158.198/32`
4. Сохранить

### Как проверить что не сломалось:

После сохранения подожди 30 секунд (Selectel применяет правила),
потом локально проверь:

```bash
ssh root@135.106.158.198 'docker compose -f /home/ozonpro/app/docker-compose.yml \
  exec -T backend python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings
asyncio.run((create_async_engine(str(settings.DATABASE_URL)).connect().__aenter__()))
print(\"DB OK\")
"'
```

Если `DB OK` — всё работает. Если ошибка `connection refused` — IP неверный, проверь правило.

### Внешний тест (опционально):

С локального компа попробуй подключиться напрямую — должно **зафейлиться**:
```bash
psql "postgresql://ozonuser:***@45.157.160.36:5432/ozonpro?sslmode=require"
# → connection refused / timeout = всё правильно, БД закрыта
```

---

## 2. DNS для flowoi.ru

Юзер сам настраивает у регистратора (Reg.ru / Beget / GoDaddy и т.п.).

**A-записи**:
```
flowoi.ru        A    135.106.158.198
www.flowoi.ru   A    135.106.158.198
```

TTL 300-3600 для быстрой проверки. После DNS-propagation (5-60 мин):

```bash
dig flowoi.ru +short
# → 135.106.158.198
```

---

## 3. SSL-сертификат (Let's Encrypt)

**На VPS**, ПОСЛЕ того как DNS указывает на 135.106.158.198:

```bash
# Один раз поставить certbot
ssh root@135.106.158.198
apt install -y certbot

# Создать webroot-папку (Let's Encrypt проверяет туда)
mkdir -p /var/www/certbot

# Временно поправить nginx чтобы пропустил ACME challenge:
# (добавить в /home/ozonpro/app/nginx/sites/ozonpro.conf):
#   location /.well-known/acme-challenge/ { root /var/www/certbot; }
# и перезапустить:
cd /home/ozonpro/app && docker compose restart nginx

# Получить сертификат
certbot certonly --webroot -w /var/www/certbot \
  -d flowoi.ru -d www.flowoi.ru \
  --email sasasamarin@gmail.com \
  --agree-tos --no-eff-email

# Сертификаты лягут в /etc/letsencrypt/live/flowoi.ru/
ls /etc/letsencrypt/live/flowoi.ru/
# → fullchain.pem privkey.pem ...

# Авто-обновление через cron (LE серты живут 90 дней)
echo '0 3 * * * certbot renew --quiet && docker exec ozon_nginx nginx -s reload' | crontab -
```

---

## 4. Активировать flowoi.conf

После получения сертификата:

```bash
cd /home/ozonpro/app
# Сохранить старый http-only конфиг
mv nginx/sites/ozonpro.conf nginx/sites/ozonpro.conf.bak

# Использовать новый HTTPS-конфиг (уже подготовлен в репо)
git pull  # подтянет flowoi.conf.template
mv nginx/sites/flowoi.conf.template nginx/sites/flowoi.conf

# Перезапустить nginx
docker compose restart nginx

# Проверить
curl -I https://flowoi.ru
# → HTTP/2 200, Strict-Transport-Security, X-Frame-Options...
```

---

## 5. Применить production .env

```bash
cd /home/ozonpro/app
cp .env .env.dev.bak                    # бэкап старого
cp .env .env

# !!! РУЧНО заменить CHANGE_ME для:
#   SECRET_KEY, FERNET_KEY, JWT_SECRET
# Команды для генерации:
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64))"
python -c "from cryptography.fernet import Fernet; print('FERNET_KEY=' + Fernet.generate_key().decode())"

# Применить
docker compose up -d --build backend frontend
docker compose restart nginx
```

---

## 6. Проверка

```bash
# Backend health
curl https://flowoi.ru/api/v1/health

# CORS работает
curl -H "Origin: https://flowoi.ru" -I https://flowoi.ru/api/v1/dashboard/

# HSTS заголовок
curl -I https://flowoi.ru | grep -i strict-transport

# SSL ssllabs score (должен быть A или A+)
# https://www.ssllabs.com/ssltest/analyze.html?d=flowoi.ru
```

---

## Чеклист

- [ ] **БЛОКЕР**: Selectel firewall закрыт на `135.106.158.198/32`
- [ ] DNS A-запись flowoi.ru → 135.106.158.198
- [ ] DNS A-запись www.flowoi.ru → 135.106.158.198
- [ ] `dig flowoi.ru +short` показывает 135.106.158.198
- [ ] certbot получил сертификат
- [ ] flowoi.conf активирован, nginx перезапущен
- [ ] .env.production применён, FERNET_KEY/SECRET_KEY/JWT_SECRET сгенерированы заново
- [ ] frontend пересобран с `VITE_API_URL=https://flowoi.ru/api/v1`
- [ ] `https://flowoi.ru` открывается, login/dashboard работают
- [ ] cron `certbot renew` настроен

---

## Что подготовлено заранее в репо

| Файл | Описание |
|---|---|
| `nginx/sites/flowoi.conf.template` | Production HTTPS-конфиг для flowoi.ru. SSL + HSTS + X-Frame-Options + Referrer-Policy + Permissions-Policy. После certbot — переименовать в `.conf`. |
| `.env.production.template` | Production env с CORS/ALLOWED_HOSTS для flowoi.ru. Перед применением — заменить CHANGE_ME-секреты. |
| `PRODUCTION_LAUNCH.md` (этот файл) | Полный пошаговый чеклист. |
