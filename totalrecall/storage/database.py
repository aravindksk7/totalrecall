import asyncpg

from totalrecall.config.settings import Settings


def to_asyncpg_dsn(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def connect(settings: Settings) -> asyncpg.Connection:
    return await asyncpg.connect(to_asyncpg_dsn(settings.database_url))


async def check_database(settings: Settings) -> bool:
    connection = await connect(settings)
    try:
        result = await connection.fetchval("select 1")
        return result == 1
    finally:
        await connection.close()
