# 🚀 ДЕПЛОЙ OZON PRO НА SELECTEL — пошагово

Цель: за 1-2 дня поднять рабочий сервер с подключёнными магазинами Озона.

---

## **📋 ЧТО У ТЕБЯ ДОЛЖНО БЫТЬ ПЕРЕД НАЧАЛОМ**

```
□ Аккаунт Selectel (пополненный на 3-5K ₽)
□ Аккаунт GitHub
□ Терминал (Mac/Linux) или MobaXterm/Putty (Windows)
□ Базовое знание SSH
□ API ключи Озона для всех 4 магазинов
□ Доменное имя (опционально, можно потом)
```

---

## **🔑 ШАГ 1: Сгенерировать SSH ключ (если ещё нет)**

На своём Mac:

```bash
# Проверь есть ли уже ключ
ls -la ~/.ssh/

# Если нет id_rsa или id_ed25519 — создай:
ssh-keygen -t ed25519 -C "твоя@почта.ru"

# Нажми Enter на все вопросы (используй пустой passphrase или придумай свой)

# Посмотри публичный ключ:
cat ~/.ssh/id_ed25519.pub
# Скопируй вывод — он понадобится в Selectel
```

---

## **🖥 ШАГ 2: Создать VPS в Selectel**

1. Зайди https://my.selectel.ru
2. **Облачные серверы → Создать сервер**

### **Настройки:**

```
├─ Регион: Санкт-Петербург (ru-3) или Москва (ru-9)
├─ Зона: любая доступная
├─ Источник: образ → Ubuntu → Ubuntu 24.04 LTS 64-bit
├─ Конфигурация:
│   ├─ vCPU: 2
│   ├─ RAM: 4 GB
│   ├─ Диск: 50 GB SSD
│   └─ Тариф: ~1,500-2,000 ₽/мес
├─ Сеть:
│   ├─ Публичный IP: ВКЛЮЧЕН
│   └─ Сегмент: автоматически
├─ SSH-ключ:
│   └─ Добавить ключ → вставить твой публичный ключ из шага 1
├─ Имя сервера: ozon-pro-prod
└─ Резервное копирование: ВКЛЮЧИТЬ (ежедневное)
```

3. **Создать сервер** → подожди 2-3 минуты пока поднимется
4. **Запиши публичный IP** сервера (например: 5.188.55.123)

---

## **💾 ШАГ 3: Создать Managed PostgreSQL**

В Selectel: **Облачные базы данных → Создать базу**

```
├─ Тип: PostgreSQL
├─ Версия: 16
├─ Регион: тот же что VPS (важно!)
├─ Конфигурация: 1 vCPU / 2 GB RAM / 20 GB
├─ Имя кластера: ozon-pro-db
├─ Имя БД: ozonpro
├─ Имя пользователя: ozonuser
├─ Пароль: придумай сложный, ЗАПИШИ
└─ Расширения: ВКЛЮЧИТЬ TimescaleDB
```

**Запиши:**
- Хост: например `ozon-pro-db.c.selcloud.ru`
- Порт: `5432`
- Пользователь: `ozonuser`
- Пароль: тот что придумал
- БД: `ozonpro`

В настройках разрешить подключение с IP твоего VPS.

---

## **🧠 ШАГ 4: Создать Managed Redis**

**Облачные базы данных → Создать → Redis**

```
├─ Версия: 7
├─ Регион: тот же
├─ Размер: минимальный (256 MB или 512 MB)
├─ Имя: ozon-pro-redis
└─ Пароль: придумай, запиши
```

**Запиши:**
- Хост и порт
- Пароль

---

## **📦 ШАГ 5: Создать S3 хранилище**

**Объектное хранилище → Создать**

```
├─ Регион: тот же
├─ Имя контейнера: ozon-pro-files
└─ Тип доступа: Приватный
```

В разделе **Управление пользователями** создай API ключи (Access Key + Secret Key) — запиши их.

---

## **🌐 ШАГ 6: Зарегистрировать домен (опционально)**

Reg.ru или nic.ru:
- Купи домен (например ozonpro.ru) — ~250-500 ₽/год
- Создай A-запись: `@ → IP твоего VPS`
- Создай A-запись: `www → IP твоего VPS`
- DNS обновится за 1-2 часа

---

## **🔐 ШАГ 7: Подключиться к серверу по SSH**

```bash
ssh root@5.188.55.123   # замени на свой IP

# Если ругается на ключ — добавь -i
ssh -i ~/.ssh/id_ed25519 root@5.188.55.123
```

После подключения:

```bash
# Обновляем систему
apt update && apt upgrade -y

# Устанавливаем Docker
curl -fsSL https://get.docker.com | sh

# Устанавливаем Docker Compose (если ещё не стоит)
apt install -y docker-compose-plugin

# Проверяем
docker --version
docker compose version

# Создаём отдельного юзера для приложения
adduser --disabled-password --gecos "" ozonpro
usermod -aG docker ozonpro

# Копируем SSH ключ для ozonpro юзера
mkdir -p /home/ozonpro/.ssh
cp /root/.ssh/authorized_keys /home/ozonpro/.ssh/
chown -R ozonpro:ozonpro /home/ozonpro/.ssh
chmod 700 /home/ozonpro/.ssh
chmod 600 /home/ozonpro/.ssh/authorized_keys

# Переключаемся на ozonpro
su - ozonpro
```

---

## **📥 ШАГ 8: Клонировать репозиторий**

```bash
# Под юзером ozonpro:
cd ~
git clone https://github.com/ТВОЙ_USERNAME/ozon-pro.git
cd ozon-pro

# Скопировать .env
cp backend/.env.example backend/.env

# Открыть в редакторе
nano backend/.env
```

### **Заполнить .env:**

```env
ENVIRONMENT=production
DEBUG=false

# Сгенерируй командой: openssl rand -hex 32
SECRET_KEY=твой_сгенерированный_ключ

# Сгенерируй командой: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=твой_fernet_ключ

# БД из шага 3
DATABASE_URL=postgresql+asyncpg://ozonuser:ПАРОЛЬ@ozon-pro-db.c.selcloud.ru:5432/ozonpro
DATABASE_URL_SYNC=postgresql://ozonuser:ПАРОЛЬ@ozon-pro-db.c.selcloud.ru:5432/ozonpro

# Redis из шага 4
REDIS_URL=redis://:ПАРОЛЬ@ozon-pro-redis.c.selcloud.ru:6379/0
CELERY_BROKER_URL=redis://:ПАРОЛЬ@ozon-pro-redis.c.selcloud.ru:6379/1
CELERY_RESULT_BACKEND=redis://:ПАРОЛЬ@ozon-pro-redis.c.selcloud.ru:6379/2

# S3 из шага 5
S3_BUCKET=ozon-pro-files
S3_ACCESS_KEY=твой_access_key
S3_SECRET_KEY=твой_secret_key

# Claude API (получи на https://console.anthropic.com)
ANTHROPIC_API_KEY=sk-ant-...

# Sentry (создай проект на sentry.io)
SENTRY_DSN=https://...@sentry.io/...

# Хосты
ALLOWED_HOSTS=твойдомен.ru,localhost
CORS_ORIGINS=https://твойдомен.ru
FRONTEND_URL=https://твойдомен.ru
```

Сохрани (Ctrl+O, Enter, Ctrl+X).

---

## **🚀 ШАГ 9: Запустить приложение**

```bash
# Запускаем всё через Docker
docker compose up -d

# Смотрим логи
docker compose logs -f backend

# Должно появиться:
# INFO     app_starting environment=production
# INFO     database_connected
# INFO     Uvicorn running on http://0.0.0.0:8000
```

### **Применить миграции БД:**

```bash
# Создаём первую миграцию (на основе моделей)
docker compose exec backend alembic revision --autogenerate -m "initial"

# Применяем
docker compose exec backend alembic upgrade head

# Превращаем нужные таблицы в TimescaleDB hypertable
docker compose exec backend python -m app.scripts.init_hypertables
```

---

## **🔒 ШАГ 10: Получить SSL сертификат**

```bash
# Установить certbot
sudo apt install -y certbot

# Остановить nginx чтобы освободить 80 порт
docker compose stop nginx

# Получить сертификат
sudo certbot certonly --standalone -d твойдомен.ru -d www.твойдомен.ru

# Запустить nginx обратно
docker compose start nginx

# Авто-обновление сертификата
sudo crontab -e
# Добавь строку:
# 0 3 * * 0 certbot renew --quiet && docker compose restart nginx
```

---

## **✅ ШАГ 11: Проверка**

```bash
# Проверка через curl
curl https://твойдомен.ru/health
# Должно вернуть: {"status":"ok"}

curl https://твойдомен.ru/api/v1/auth/register \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.ru","password":"password123","full_name":"Test User","company_name":"Test Co"}'

# Должно вернуть токены
```

---

## **📊 ШАГ 12: Подключить 4 магазина Озона**

```bash
# Сначала логин — сохрани access_token
curl https://твойдомен.ru/api/v1/auth/login \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.ru","password":"password123"}'

# Подключи первый магазин
curl https://твойдомен.ru/api/v1/ozon-accounts/ \
  -X POST \
  -H "Authorization: Bearer ТВОЙ_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "STOLZ KRAFT",
    "client_id": "твой_client_id",
    "api_key": "твой_api_key"
  }'

# Запусти первую синхронизацию
curl https://твойдомен.ru/api/v1/ozon-accounts/UUID_МАГАЗИНА/sync \
  -X POST \
  -H "Authorization: Bearer ТВОЙ_ACCESS_TOKEN"
```

Или используй веб-интерфейс по адресу `https://твойдомен.ru/api/docs` (Swagger UI) — там удобнее.

---

## **🎯 РЕЗУЛЬТАТ**

После этих 12 шагов у тебя будет:

```
✅ Сервер работает в РФ (Selectel)
✅ БД хранит данные за годы (TimescaleDB)
✅ 4 магазина Озона подключены
✅ Данные тянутся автоматически (каждый час)
✅ Логируется каждый шаг
✅ Sentry ловит ошибки
✅ API доступен на твоём домене
✅ SSL сертификат работает
```

**Следующий шаг:** добавить frontend React и Dashboard.

---

## **🐛 ЕСЛИ ЧТО-ТО НЕ РАБОТАЕТ**

```bash
# Логи backend
docker compose logs -f backend

# Логи Celery worker
docker compose logs -f worker

# Логи nginx
docker compose logs -f nginx

# Зайти внутрь контейнера
docker compose exec backend bash

# Перезапустить всё
docker compose restart

# Полная остановка
docker compose down

# Полная остановка + удаление томов (ОСТОРОЖНО!)
docker compose down -v
```

**Любая ошибка — присылай вывод логов и я подскажу.**
