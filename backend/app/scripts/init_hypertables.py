"""
Превращает обычные таблицы во временные ряды TimescaleDB.

Запускать ОДИН РАЗ после первой миграции Alembic:
    docker-compose exec backend python -m app.scripts.init_hypertables
"""
import asyncio

from sqlalchemy import text

from app.core.logging import log, setup_logging
from app.db.session import engine


HYPERTABLES = [
    # (table_name, time_column, chunk_interval)
    ("price_history", "time", "7 days"),
    ("stocks", "time", "7 days"),
    ("transactions", "time", "30 days"),
    ("analytics_daily", "date", "30 days"),
]


async def create_hypertables() -> None:
    """Превращаем нужные таблицы в hypertable."""
    setup_logging()

    async with engine.connect() as conn:
        for table, time_col, interval in HYPERTABLES:
            try:
                # Проверяем существует ли уже hypertable
                check_sql = text(
                    "SELECT 1 FROM timescaledb_information.hypertables "
                    "WHERE hypertable_name = :name"
                )
                result = await conn.execute(check_sql, {"name": table})
                exists = result.scalar() is not None

                if exists:
                    log.info("hypertable_already_exists", table=table)
                    continue

                # Создаём hypertable
                sql = text(
                    f"SELECT create_hypertable("
                    f"  '{table}', '{time_col}', "
                    f"  chunk_time_interval => INTERVAL '{interval}', "
                    f"  if_not_exists => TRUE, "
                    f"  migrate_data => TRUE"
                    f")"
                )
                await conn.execute(sql)
                await conn.commit()
                log.info("hypertable_created", table=table, interval=interval)

                # Включаем компрессию для экономии места (старше 30 дней)
                compress_sql = text(
                    f"ALTER TABLE {table} SET ("
                    f"  timescaledb.compress, "
                    f"  timescaledb.compress_segmentby = 'product_id'"
                    f")"
                )
                try:
                    await conn.execute(compress_sql)
                    await conn.execute(text(
                        f"SELECT add_compression_policy("
                        f"  '{table}', INTERVAL '30 days', if_not_exists => TRUE"
                        f")"
                    ))
                    await conn.commit()
                    log.info("compression_enabled", table=table)
                except Exception as e:
                    log.warning("compression_setup_failed", table=table, error=str(e))

            except Exception as e:
                log.error("hypertable_creation_failed", table=table, error=str(e))


if __name__ == "__main__":
    asyncio.run(create_hypertables())
