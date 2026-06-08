"""
Главное FastAPI приложение.

Запуск:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.api.routes import api_router
from app.core.config import settings
from routers.sales_plan import router as sales_plan_router
from app.core.logging import log, setup_logging
from app.db.session import check_db_connection, engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Действия при запуске / остановке приложения."""
    # === STARTUP ===
    setup_logging()
    log.info(
        "app_starting",
        environment=settings.ENVIRONMENT,
        debug=settings.DEBUG,
    )

    # Sentry для отслеживания ошибок
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.SENTRY_ENVIRONMENT,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            integrations=[
                FastApiIntegration(),
                SqlalchemyIntegration(),
            ],
        )
        log.info("sentry_initialized")

    # Проверяем БД
    db_ok = await check_db_connection()
    if db_ok:
        log.info("database_connected")
    else:
        log.error("database_not_available")

    yield  # === приложение работает ===

    # === SHUTDOWN ===
    log.info("app_shutting_down")
    await engine.dispose()


# Создаём FastAPI приложение
app = FastAPI(
    title="Flowoi API",
    description="Финансовый мозг для селлеров маркетплейсов",
    version="0.1.0",
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url="/api/redoc" if not settings.is_production else None,
    openapi_url="/api/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

# CORS — разрешаем запросы с фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,  # type: ignore
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем все API endpoints
app.include_router(api_router, prefix="/api/v1")
app.include_router(sales_plan_router, prefix="/api/v1/plan", tags=["plan"])


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    """Корневой endpoint."""
    return {
        "name": "Flowoi API",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Простой health check."""
    return {"status": "ok"}


@app.get("/health/db", tags=["health"])
async def health_db() -> dict[str, str | bool]:
    """Health check БД."""
    is_ok = await check_db_connection()
    return {
        "status": "ok" if is_ok else "error",
        "database": is_ok,
    }
