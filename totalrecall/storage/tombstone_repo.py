"""Postgres-backed tombstone repository."""

import asyncpg


class PostgresTombstoneRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def add(
        self,
        tenant_id: str,
        application_id: str,
        entity_id: str,
        deleted_by: str,
        reason: str | None = None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                insert into memory_tombstones
                    (memory_id, tenant_id, application_id, reason, deleted_by)
                values ($1, $2, $3, $4, $5)
                on conflict (memory_id) do nothing
                """,
                entity_id,
                tenant_id,
                application_id,
                reason,
                deleted_by,
            )

    async def load_all(self) -> list[tuple[str, str, str]]:
        """Return all (tenant_id, application_id, memory_id) tuples for startup preload."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "select tenant_id, application_id, memory_id from memory_tombstones"
            )
        return [(r["tenant_id"], r["application_id"], r["memory_id"]) for r in rows]

    async def exists(self, tenant_id: str, application_id: str, entity_id: str) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                select 1 from memory_tombstones
                where memory_id = $1 and tenant_id = $2 and application_id = $3
                """,
                entity_id,
                tenant_id,
                application_id,
            )
        return row is not None
