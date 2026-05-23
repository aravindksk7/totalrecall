"""Postgres-backed repository for memory adapter provider mappings.

Stores the external provider_id (e.g. Mem0 user ID) and adapter version
for each tenant/application pair so they can be retrieved for reproducibility
and debugging without re-computing them from first principles.
"""

import json
from typing import Any

import asyncpg


class PostgresProviderMappingRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def upsert(
        self,
        tenant_id: str,
        application_id: str,
        adapter_version: str,
        provider_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Insert or update the provider mapping for a tenant/application/adapter triple."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO adapter_version_mappings
                    (tenant_id, application_id, adapter_version, provider_id, metadata, updated_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (tenant_id, application_id, adapter_version) DO UPDATE SET
                    provider_id     = EXCLUDED.provider_id,
                    metadata        = EXCLUDED.metadata,
                    updated_at      = NOW()
                RETURNING *
                """,
                tenant_id,
                application_id,
                adapter_version,
                provider_id,
                json.dumps(metadata or {}),
            )
        return dict(row)

    async def get(
        self,
        tenant_id: str,
        application_id: str,
        adapter_version: str,
    ) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM adapter_version_mappings
                WHERE tenant_id = $1
                  AND application_id = $2
                  AND adapter_version = $3
                """,
                tenant_id,
                application_id,
                adapter_version,
            )
        return dict(row) if row else None

    async def list_for_tenant(self, tenant_id: str) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM adapter_version_mappings
                WHERE tenant_id = $1
                ORDER BY application_id, adapter_version
                """,
                tenant_id,
            )
        return [dict(r) for r in rows]
