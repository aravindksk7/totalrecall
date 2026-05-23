"""Postgres-backed catalogue repository."""

import json
import uuid
from typing import Any

import asyncpg

from totalrecall.catalogue.models import (
    CatalogueCategory,
    CatalogueEntry,
    CatalogueSearchFilters,
    CatalogueSearchResult,
    CatalogueSource,
    CatalogueStatus,
)


class PostgresCatalogueRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def search(self, filters: CatalogueSearchFilters) -> CatalogueSearchResult:
        conditions = ["tenant_id = $1"]
        params: list[Any] = [filters.tenant_id]
        idx = 2

        if filters.application_id:
            conditions.append(f"application_id = ${idx}")
            params.append(filters.application_id)
            idx += 1

        if filters.category:
            conditions.append(f"category = ${idx}")
            params.append(filters.category.value)
            idx += 1

        if filters.status:
            conditions.append(f"status = ${idx}")
            params.append(filters.status.value)
            idx += 1

        where = " and ".join(conditions)
        query = (
            f"select * from catalogue_entries where {where} "
            f"order by updated_at desc limit ${idx} offset ${idx + 1}"
        )
        params.extend([filters.limit, filters.offset])

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            count_row = await conn.fetchrow(
                f"select count(*) from catalogue_entries where {where}",
                *params[:-2],
            )

        entries = [self._row_to_entry(r) for r in rows]
        return CatalogueSearchResult(items=entries, total=count_row["count"])

    async def get(self, tenant_id: str, entity_id: str) -> CatalogueEntry | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "select * from catalogue_entries where id = $1 and tenant_id = $2",
                entity_id,
                tenant_id,
            )
        return self._row_to_entry(row) if row else None

    async def upsert(self, entry: CatalogueEntry) -> CatalogueEntry:
        entity_id = entry.entity_id if entry.entity_id else str(uuid.uuid4())
        source_json = entry.source.model_dump(mode="json") if entry.source else {}
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                insert into catalogue_entries
                    (id, tenant_id, application_id, category, status, summary, source, tags,
                     owner, approved_by, approved_at, deleted_by, deleted_at)
                values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                on conflict (id) do update set
                    status      = excluded.status,
                    summary     = excluded.summary,
                    source      = excluded.source,
                    tags        = excluded.tags,
                    owner       = excluded.owner,
                    approved_by = excluded.approved_by,
                    approved_at = excluded.approved_at,
                    deleted_by  = excluded.deleted_by,
                    deleted_at  = excluded.deleted_at,
                    updated_at  = now()
                """,
                entity_id,
                entry.tenant_id,
                entry.application_id,
                entry.category.value,
                entry.status.value,
                entry.summary,
                json.dumps(source_json),
                json.dumps(entry.tags),
                entry.owner,
                entry.approved_by,
                entry.approved_at,
                entry.deleted_by,
                entry.deleted_at,
            )
        return entry.model_copy(update={"entity_id": entity_id})

    async def update_status(
        self, tenant_id: str, entity_id: str, status: CatalogueStatus
    ) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                update catalogue_entries
                set status = $1, updated_at = now()
                where id = $2 and tenant_id = $3
                """,
                status.value,
                entity_id,
                tenant_id,
            )
        return result != "UPDATE 0"

    @staticmethod
    def _row_to_entry(row: asyncpg.Record) -> CatalogueEntry:
        source_raw = row["source"]
        if isinstance(source_raw, str):
            source_raw = json.loads(source_raw)
        tags_raw = row["tags"]
        if isinstance(tags_raw, str):
            tags_raw = json.loads(tags_raw)

        source = None
        if source_raw and source_raw.get("type") and source_raw.get("reference"):
            source = CatalogueSource(**source_raw)

        return CatalogueEntry(
            entity_id=row["id"],
            tenant_id=row["tenant_id"],
            application_id=row["application_id"],
            category=CatalogueCategory(row["category"]),
            status=CatalogueStatus(row["status"]),
            summary=row["summary"],
            source=source,
            tags=tags_raw or {},
            owner=row.get("owner"),
            approved_by=row.get("approved_by"),
            approved_at=row.get("approved_at"),
            deleted_by=row.get("deleted_by"),
            deleted_at=row.get("deleted_at"),
        )
