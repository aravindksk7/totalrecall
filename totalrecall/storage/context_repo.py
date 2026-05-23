"""Postgres repository for context snapshots."""

import json

import asyncpg


class PostgresContextSnapshotRepository:
    """Persists context snapshots so generations can be reproduced."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def save(
        self,
        snapshot_id: str,
        tenant_id: str,
        application_id: str,
        request_id: str,
        skill_ids: list[str],
        memory_ids: list[str],
        estimated_input_tokens: int,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO context_snapshots
                    (id, tenant_id, application_id, request_id,
                     skill_ids, memory_ids, estimated_input_tokens)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7)
                ON CONFLICT (id) DO NOTHING
                """,
                snapshot_id,
                tenant_id,
                application_id,
                request_id,
                json.dumps(skill_ids),
                json.dumps(memory_ids),
                estimated_input_tokens,
            )

    async def get_by_request_id(
        self, tenant_id: str, request_id: str
    ) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, tenant_id, application_id, request_id,
                       skill_ids, memory_ids, estimated_input_tokens, created_at
                FROM context_snapshots
                WHERE tenant_id = $1 AND request_id = $2
                """,
                tenant_id,
                request_id,
            )
        if row is None:
            return None
        return {
            "snapshot_id": row["id"],
            "tenant_id": row["tenant_id"],
            "application_id": row["application_id"],
            "request_id": row["request_id"],
            "skill_ids": row["skill_ids"],
            "memory_ids": row["memory_ids"],
            "estimated_input_tokens": row["estimated_input_tokens"],
            "created_at": row["created_at"].isoformat(),
        }
