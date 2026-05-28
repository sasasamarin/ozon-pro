"""
Подключение к PostgreSQL через async SQLAlchemy.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import log


def make_engine_and_session(
    *,
    pool_size: int | None = None,
    max_overflow: int | None = None,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """
    Создать новую пару (engine, AsyncSessionLocal).

    Используется в Celery-тасках, чтобы каждая задача получала engine,
    привязанный к свежему event loop'у (`asyncio.run()` создаёт новый loop
    каждый вызов, а asyncpg-engine из предыдущего loop'а ломается с
    «Task attached to a different loop»).

    Для FastAPI engine создаётся один раз на модуль-импорт (см. ниже).
    """
    eng = create_async_engine(
        str(settings.DATABASE_URL),
        pool_size=pool_size if pool_size is not None else settings.DB_POOL_SIZE,
        max_overflow=max_overflow if max_overflow is not None else settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=settings.DEBUG and not settings.is_production,
    )
    factory = async_sessionmaker(
        bind=eng,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    return eng, factory


# Глобальный engine для FastAPI (uvicorn держит один event loop)
engine, AsyncSessionLocal = make_engine_and_session()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для FastAPI — получить сессию БД.

    Использование:
        @router.get("/")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            log.error("db_session_error", error=str(e))
            raise
        finally:
            await session.close()


async def check_db_connection() -> bool:
    """Проверка что БД доступна (для health check)."""
    try:
        async with engine.connect() as conn:
            from sqlalchemy import text
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        log.error("db_health_check_failed", error=str(e))
        return False
