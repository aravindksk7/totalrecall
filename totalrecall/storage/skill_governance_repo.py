"""Postgres-backed skill governance repository.

Stores runtime status overrides for file-backed skills. Records here take
precedence over the status field in the skill's JSON definition.
"""

import asyncpg


class PostgresSkillGovernanceRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def upsert(
        self,
        skill_id: str,
        version: str,
        status: str,
        promoted_by: str,
        notes: str | None = None,
    ) -> dict:
        """Insert or update a governance record; sets promoted_at when status → active."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO skill_governance
                    (skill_id, version, status, promoted_by, promoted_at, notes, updated_at)
                VALUES (
                    $1, $2, $3, $4,
                    CASE WHEN $3 = 'active' THEN NOW() ELSE NULL END,
                    $5,
                    NOW()
                )
                ON CONFLICT (skill_id, version) DO UPDATE SET
                    status      = EXCLUDED.status,
                    promoted_by = EXCLUDED.promoted_by,
                    promoted_at = CASE
                                    WHEN EXCLUDED.status = 'active' THEN NOW()
                                    ELSE skill_governance.promoted_at
                                  END,
                    notes       = EXCLUDED.notes,
                    updated_at  = NOW()
                RETURNING *
                """,
                skill_id,
                version,
                status,
                promoted_by,
                notes,
            )
        return dict(row)

    async def get(self, skill_id: str, version: str) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM skill_governance WHERE skill_id = $1 AND version = $2",
                skill_id,
                version,
            )
        return dict(row) if row else None

    async def list_all(self) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM skill_governance ORDER BY skill_id, version"
            )
        return [dict(r) for r in rows]

    async def load_overrides(self) -> dict[str, str]:
        """Return {skill_id: status} for all records; most-recently-updated wins per skill_id."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT skill_id, status FROM skill_governance ORDER BY updated_at DESC"
            )
        overrides: dict[str, str] = {}
        for r in rows:
            if r["skill_id"] not in overrides:
                overrides[r["skill_id"]] = r["status"]
        return overrides
