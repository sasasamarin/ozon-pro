-- ============================================
-- Инициализация TimescaleDB
-- Запускается автоматически при первом старте контейнера
-- ============================================

-- Включаем расширение TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Включаем pg_trgm для полнотекстового поиска
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Расширение для UUID
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================
-- Hypertables создаются ПОСЛЕ Alembic миграций
-- через отдельный скрипт (см. backend/scripts/init_hypertables.py)
-- ============================================
