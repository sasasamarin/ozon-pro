"""
Логирование (структурированное, JSON формат для production).

ВАЖНО: каждое обращение к Озон API логируется со всеми параметрами,
чтобы видеть когда API упал, какие данные не загрузились.
"""
import logging
import sys
from typing import Any

import structlog

from app.core.config import settings


def setup_logging() -> None:
    """Настроить structlog для всего приложения."""

    # Стандартный logging тоже настраиваем
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=settings.LOG_LEVEL,
    )

    # Процессоры (в production — JSON, в dev — красивые цвета)
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.is_production:
        # В production — JSON для удобной обработки (Grafana Loki и т.д.)
        processors.append(structlog.processors.JSONRenderer())
    else:
        # В dev — красивый вывод
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL, logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """Получить логгер для модуля."""
    return structlog.get_logger(name)


# Главный логгер приложения
log = get_logger("ozon_pro")
