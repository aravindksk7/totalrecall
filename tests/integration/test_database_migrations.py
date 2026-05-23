import os

import pytest

from totalrecall.config.settings import Settings
from totalrecall.storage.database import check_database
from totalrecall.storage.migrations import apply_migrations

pytestmark = pytest.mark.postgres


@pytest.mark.asyncio
async def test_postgres_migrations_apply_when_enabled() -> None:
    if os.getenv("TOTALRECALL_RUN_DATABASE_TESTS") != "1":
        pytest.skip("Postgres integration tests are disabled outside Docker.")

    settings = Settings()

    await apply_migrations(settings)

    assert await check_database(settings) is True
