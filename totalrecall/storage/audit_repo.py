"""Postgres-backed audit event repository."""

import json
import uuid
from typing import Any

import asyncpg


class PostgresAuditRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def record(
        self,
        tenant_id: str,
        actor_id: str,
        event_type: str,
        subject_type: str,
        subject_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> str:
        event_id = str(uuid.uuid4())
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                insert into audit_events
                    (id, tenant_id, actor_id, event_type, subject_type, subject_id, details)
                values ($1, $2, $3, $4, $5, $6, $7)
                """,
                event_id,
                tenant_id,
                actor_id,
                event_type,
                subject_type,
                subject_id,
                json.dumps(details or {}),
            )
        return event_id

    async def recent(
        self, tenant_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select id, actor_id, event_type, subject_type, subject_id, details, created_at
                from audit_events
                where tenant_id = $1
                order by created_at desc
                limit $2
                """,
                tenant_id,
                limit,
            )
        return [dict(r) for r in rows]
