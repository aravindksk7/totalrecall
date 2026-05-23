"""asyncpg connection pool lifecycle for the FastAPI application."""

import logging

import asyncpg

from totalrecall.storage.database import to_asyncpg_dsn

logger = logging.getLogger(__name__)


async def create_pool(database_url: str) -> asyncpg.Pool | None:
    """Create an asyncpg pool; returns None if the database is unreachable."""
    dsn = to_asyncpg_dsn(database_url)
    try:
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10)
        logger.info("Database pool created.")
        return pool
    except Exception as exc:
        logger.warning("Database pool creation failed — running without database: %s", exc)
        return None


async def close_pool(pool: asyncpg.Pool | None) -> None:
    if pool is not None:
        await pool.close()
        logger.info("Database pool closed.")
