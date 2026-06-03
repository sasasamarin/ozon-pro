"""
Конфигурация приложения.
Все настройки читаются из .env через pydantic-settings.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Главные настройки приложения. Все значения из .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- ОКРУЖЕНИЕ ---
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # --- БЕЗОПАСНОСТЬ ---
    SECRET_KEY: str = Field(..., min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    ENCRYPTION_KEY: str  # Fernet ключ для шифрования API ключей Озона

    # --- БАЗА ДАННЫХ ---
    DATABASE_URL: PostgresDsn
    DATABASE_URL_SYNC: PostgresDsn  # для Alembic
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # --- REDIS ---
    REDIS_URL: RedisDsn
    CELERY_BROKER_URL: RedisDsn
    CELERY_RESULT_BACKEND: RedisDsn

    # --- S3 ---
    S3_ENDPOINT_URL: str = "https://s3.selcdn.ru"
    S3_BUCKET: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_REGION: str = "ru-1"

    # --- CLAUDE AI ---
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL_HAIKU: str = "claude-haiku-4-5"
    CLAUDE_MODEL_SONNET: str = "claude-sonnet-4-6"
    CLAUDE_MODEL_OPUS: str = "claude-opus-4-7"
    # Прокси к Anthropic для VPS в РФ. Если задан — все AI-вызовы через него.
    # Прокси принимает {model, messages, tools, system} и возвращает Anthropic-формат.
    AI_PROXY_URL: str = ""
    AI_PROXY_TOKEN: str = ""
    AI_DEFAULT_MODEL: str = "claude-sonnet-4-6"
    AI_MAX_TOOL_ITERATIONS: int = 6  # защита от бесконечного tool-цикла

    # AI Phase 1 (FLOWOI_AI_TZ §8): OpenAI для function calling.
    # Ключ ТОЛЬКО на бэкенде (env), фронт не видит. Если не задан — endpoint
    # отдаёт 503 с инструкцией добавить ключ.
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = ""  # пусто = https://api.openai.com/v1. Можно прокси.
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_MAX_TOOL_ITERATIONS: int = 6

    # --- SENTRY ---
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "development"
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # --- EMAIL ---
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "noreply@flowoi.ru"
    EMAIL_FROM_NAME: str = "Flowoi"

    # --- TELEGRAM ---
    TELEGRAM_BOT_TOKEN: str = ""

    # --- ОЗОН API ---
    OZON_API_BASE_URL: str = "https://api-seller.ozon.ru"
    OZON_PERFORMANCE_API_BASE_URL: str = "https://api-performance.ozon.ru"
    OZON_WEBHOOK_SECRET: str = ""

    # --- RATE LIMITS ---
    RATE_LIMIT_FREE: int = 100
    RATE_LIMIT_STARTER: int = 1000
    RATE_LIMIT_PRO: int = 5000
    RATE_LIMIT_BUSINESS: int = 20000

    # --- AI LIMITS (per month, per user) ---
    # Старт: 50 запросов на gpt_4o_mini
    AI_LIMIT_START_MINI: int = 50
    # Pro: 500 mini + 50 gpt_4o
    AI_LIMIT_PRO_MINI: int = 500
    AI_LIMIT_PRO_GPT4O: int = 50
    # Business: 2000 mini + неограниченно gpt_4o (-1 = без лимита)
    AI_LIMIT_BUSINESS_MINI: int = 2000
    AI_LIMIT_BUSINESS_GPT4O: int = -1

    # --- ХОСТЫ ---
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"
    CORS_ORIGINS: str = "http://localhost:5173"
    FRONTEND_URL: str = "http://localhost:5173"

    @field_validator("ALLOWED_HOSTS", "CORS_ORIGINS")
    @classmethod
    def split_csv(cls, v: str) -> list[str]:
        """Превращаем CSV строку в список."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    """Получить настройки (кэшированно для скорости)."""
    return Settings()  # type: ignore


# Глобальный объект настроек
settings = get_settings()
