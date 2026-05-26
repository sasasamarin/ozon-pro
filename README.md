# 🚀 Ozon Pro — SaaS для селлеров маркетплейсов

**Финансовый мозг твоего маркетплейс-бизнеса.**
Все магазины + кредиты + расходы вне Озона + AI-помощник.

---

## 📋 Стек

```
BACKEND:  Python 3.11 + FastAPI + SQLAlchemy + Celery
FRONTEND: React 18 + TypeScript + Vite + Tailwind
БД:       PostgreSQL 16 + TimescaleDB + Redis 7
ХОСТИНГ:  Selectel (Россия)
AI:       Claude API (Anthropic)
```

---

## 🏗 Структура проекта

```
ozon-pro/
├── backend/
│   ├── app/
│   │   ├── api/           # API endpoints (FastAPI routers)
│   │   ├── core/          # Конфиг, безопасность, логи
│   │   ├── db/            # Подключение к БД
│   │   ├── models/        # SQLAlchemy модели
│   │   ├── schemas/       # Pydantic схемы
│   │   ├── services/      # Бизнес-логика
│   │   ├── workers/       # Celery задачи
│   │   └── utils/         # Утилиты
│   ├── alembic/           # Миграции БД
│   ├── tests/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── .env.example
├── frontend/
│   ├── src/
│   ├── package.json
│   └── Dockerfile
├── nginx/
│   └── nginx.conf
├── docker-compose.yml
└── README.md
```

---

## 🚀 Быстрый старт (на сервере)

```bash
# 1. Клонировать
git clone https://github.com/USERNAME/ozon-pro.git
cd ozon-pro

# 2. Создать .env из примера
cp backend/.env.example backend/.env
# отредактировать .env, вписать реальные значения

# 3. Запустить всё через Docker
docker-compose up -d

# 4. Применить миграции БД
docker-compose exec backend alembic upgrade head

# 5. Создать первого пользователя
docker-compose exec backend python -m app.cli create-admin

# 6. Открыть в браузере
# https://твой-домен.ru
# API docs: https://твой-домен.ru/api/docs
```

---

## 📚 Документация

- [Архитектура](./docs/architecture.md)
- [API endpoints](./docs/api.md)
- [Схема БД](./docs/database.md)
- [Деплой](./docs/deploy.md)
