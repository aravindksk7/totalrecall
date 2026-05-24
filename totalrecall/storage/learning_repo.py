"""Postgres-backed learning run and discovery repository."""

import json
from datetime import UTC, datetime
from typing import Any

import asyncpg

from totalrecall.catalogue.models import CatalogueSource
from totalrecall.learning.models import (
    BulkDecisionResult,
    DiscoverySearchResult,
    LearningApproval,
    LearningApprovalDecision,
    LearningDelta,
    LearningDeltaState,
    LearningDiscovery,
    LearningDiscoveryStatus,
    LearningDiscoveryType,
    LearningReport,
    LearningRun,
    LearningRunStatus,
    LearningScope,
    LearningTriggerType,
)


class PostgresLearningRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def save_report(self, report: LearningReport) -> None:
        run = report.run
        scope_json = run.scope.model_dump_json()
        summary_json = json.dumps(
            {
                "discovered_count": report.discovered_count,
                "changed_count": report.changed_count,
                "removed_count": report.removed_count,
                "unchanged_count": report.unchanged_count,
                "rejected_count": report.rejected_count,
                "warnings": report.warnings,
            }
        )

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    insert into learning_runs
                        (id, tenant_id, application_id, scope, trigger_type, status, summary,
                         started_at, completed_at)
                    values ($1,$2,$3,$4::jsonb,$5,$6,$7::jsonb,$8,$9)
                    on conflict (id) do update set
                        status = excluded.status,
                        summary = excluded.summary,
                        completed_at = excluded.completed_at
                    """,
                    run.run_id,
                    run.tenant_id,
                    run.application_id,
                    scope_json,
                    run.trigger_type.value,
                    run.status.value,
                    summary_json,
                    run.started_at,
                    run.completed_at,
                )

                for discovery in run.discoveries:
                    source_json = discovery.source.model_dump_json()
                    tags_json = json.dumps(discovery.proposed_tags)
                    warnings_json = json.dumps(discovery.warnings)

                    await conn.execute(
                        """
                        insert into learning_discoveries
                            (id, run_id, tenant_id, application_id, discovery_type, status,
                             delta_state, summary, confidence, source, proposed_tags,
                             content_hash, warnings)
                        values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,$12,$13::jsonb)
                        on conflict (id) do nothing
                        """,
                        discovery.discovery_id,
                        run.run_id,
                        run.tenant_id,
                        run.application_id,
                        discovery.discovery_type.value,
                        discovery.status.value,
                        discovery.delta.state.value,
                        discovery.summary,
                        discovery.confidence,
                        source_json,
                        tags_json,
                        discovery.delta.current_hash,
                        warnings_json,
                    )

    async def get_run(self, tenant_id: str, run_id: str) -> LearningReport | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "select * from learning_runs where id=$1 and tenant_id=$2",
                run_id,
                tenant_id,
            )
            if row is None:
                return None

            discovery_rows = await conn.fetch(
                "select * from learning_discoveries where run_id=$1 order by created_at",
                run_id,
            )

        return self._rows_to_report(row, discovery_rows)

    async def list_runs(
        self, tenant_id: str, application_id: str | None = None, limit: int = 20
    ) -> list[LearningReport]:
        async with self._pool.acquire() as conn:
            if application_id:
                rows = await conn.fetch(
                    """
                    select * from learning_runs
                    where tenant_id=$1 and application_id=$2
                    order by started_at desc limit $3
                    """,
                    tenant_id,
                    application_id,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    select * from learning_runs where tenant_id=$1
                    order by started_at desc limit $2
                    """,
                    tenant_id,
                    limit,
                )

            run_ids = [r["id"] for r in rows]
            if not run_ids:
                return []

            discovery_rows = await conn.fetch(
                "select * from learning_discoveries where run_id = any($1::text[]) order by created_at",  # noqa: E501
                run_ids,
            )

        discoveries_by_run: dict[str, list[Any]] = {}
        for d in discovery_rows:
            discoveries_by_run.setdefault(d["run_id"], []).append(d)

        return [
            self._rows_to_report(row, discoveries_by_run.get(row["id"], []))
            for row in rows
        ]

    async def get_previous_hashes(self, tenant_id: str, application_id: str) -> dict[str, str]:
        """Return stable_key → content_hash from the most-recent completed run."""
        async with self._pool.acquire() as conn:
            run_row = await conn.fetchrow(
                """
                select id from learning_runs
                where tenant_id=$1 and application_id=$2 and status='completed'
                order by completed_at desc limit 1
                """,
                tenant_id,
                application_id,
            )
            if run_row is None:
                return {}

            rows = await conn.fetch(
                """
                select source, content_hash from learning_discoveries
                where run_id=$1 and content_hash is not null
                """,
                run_row["id"],
            )

        result: dict[str, str] = {}
        for row in rows:
            source = _parse_json(row["source"])
            file_path = source.get("file_path") or source.get("reference", "")
            symbol = source.get("symbol_name", "")
            stable_key = f"{file_path}::{symbol}"
            if row["content_hash"]:
                result[stable_key] = row["content_hash"]
        return result

    async def get_discovery(
        self, tenant_id: str, discovery_id: str
    ) -> tuple[LearningDiscovery, str] | None:
        """Return (discovery, application_id) or None if not found."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "select * from learning_discoveries where id=$1 and tenant_id=$2",
                discovery_id,
                tenant_id,
            )
            if row is None:
                return None
        return self._row_to_discovery(row), row["application_id"]

    async def approve_discovery(
        self, tenant_id: str, discovery_id: str, actor_id: str, reason: str | None = None
    ) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                update learning_discoveries
                set status='approved', approved_by=$1, approved_at=$2, updated_at=$2
                where id=$3 and tenant_id=$4 and status='discovered'
                """,
                actor_id,
                datetime.now(UTC),
                discovery_id,
                tenant_id,
            )
        return result != "UPDATE 0"

    async def reject_discovery(
        self, tenant_id: str, discovery_id: str, actor_id: str, reason: str | None = None
    ) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                update learning_discoveries
                set status='rejected', approved_by=$1, approved_at=$2,
                    rejection_reason=$3, updated_at=$2
                where id=$4 and tenant_id=$5 and status='discovered'
                """,
                actor_id,
                datetime.now(UTC),
                reason,
                discovery_id,
                tenant_id,
            )
        return result != "UPDATE 0"

    async def search_discoveries(
        self,
        tenant_id: str,
        *,
        q: str | None = None,
        status: str | None = None,
        discovery_type: str | None = None,
        confidence_min: float | None = None,
        run_id: str | None = None,
        limit: int = 50,
    ) -> list[DiscoverySearchResult]:
        conditions = ["d.tenant_id = $1"]
        params: list[Any] = [tenant_id]
        idx = 2

        if q:
            conditions.append(f"d.summary ILIKE '%' || ${idx} || '%'")
            params.append(q)
            idx += 1
        if status:
            conditions.append(f"d.status = ${idx}")
            params.append(status)
            idx += 1
        if discovery_type:
            conditions.append(f"d.discovery_type = ${idx}")
            params.append(discovery_type)
            idx += 1
        if confidence_min is not None:
            conditions.append(f"d.confidence >= ${idx}")
            params.append(confidence_min)
            idx += 1
        if run_id:
            conditions.append(f"d.run_id = ${idx}")
            params.append(run_id)
            idx += 1

        where = " AND ".join(conditions)
        sql = f"""
            SELECT d.*, d.run_id AS _run_id
            FROM learning_discoveries d
            WHERE {where}
            ORDER BY d.created_at DESC
            LIMIT ${idx}
        """
        params.append(limit)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        results = []
        for row in rows:
            approval: LearningApproval | None = None
            if row["approved_by"]:
                approval = LearningApproval(
                    decision=(
                        LearningApprovalDecision.APPROVED
                        if row["status"] == "approved"
                        else LearningApprovalDecision.REJECTED
                    ),
                    actor_id=row["approved_by"],
                    decided_at=row["approved_at"] or datetime.now(UTC),
                    reason=row.get("rejection_reason"),
                )
            warnings_data = _parse_json(row["warnings"])
            results.append(
                DiscoverySearchResult(
                    discovery_id=row["id"],
                    run_id=row["run_id"],
                    application_id=row["application_id"],
                    discovery_type=LearningDiscoveryType(row["discovery_type"]),
                    status=LearningDiscoveryStatus(row["status"]),
                    summary=row["summary"],
                    confidence=row["confidence"],
                    delta_state=LearningDeltaState(row["delta_state"]),
                    warnings=warnings_data if isinstance(warnings_data, list) else [],
                    approval=approval,
                )
            )
        return results

    async def bulk_approve_discoveries(
        self,
        tenant_id: str,
        discovery_ids: list[str],
        actor_id: str,
        reason: str | None = None,
    ) -> BulkDecisionResult:
        if not discovery_ids:
            return BulkDecisionResult(processed=0, skipped=0)
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                UPDATE learning_discoveries
                SET status='approved', approved_by=$1, approved_at=$2, updated_at=$2
                WHERE id = ANY($3::text[]) AND tenant_id=$4 AND status='discovered'
                RETURNING id
                """,
                actor_id,
                now,
                discovery_ids,
                tenant_id,
            )
        approved_ids = [r["id"] for r in rows]
        return BulkDecisionResult(
            processed=len(approved_ids),
            skipped=len(discovery_ids) - len(approved_ids),
            discovery_ids=approved_ids,
        )

    async def bulk_reject_discoveries(
        self,
        tenant_id: str,
        discovery_ids: list[str],
        actor_id: str,
        reason: str | None = None,
    ) -> BulkDecisionResult:
        if not discovery_ids:
            return BulkDecisionResult(processed=0, skipped=0)
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                UPDATE learning_discoveries
                SET status='rejected', approved_by=$1, approved_at=$2,
                    rejection_reason=$3, updated_at=$2
                WHERE id = ANY($4::text[]) AND tenant_id=$5 AND status='discovered'
                RETURNING id
                """,
                actor_id,
                now,
                reason,
                discovery_ids,
                tenant_id,
            )
        rejected_ids = [r["id"] for r in rows]
        return BulkDecisionResult(
            processed=len(rejected_ids),
            skipped=len(discovery_ids) - len(rejected_ids),
            discovery_ids=rejected_ids,
        )

    def _rows_to_report(self, run_row: Any, discovery_rows: list[Any]) -> LearningReport:
        scope_data = _parse_json(run_row["scope"])
        summary_data = _parse_json(run_row["summary"])

        scope = LearningScope(
            repository=scope_data.get("repository", "local"),
            branch=scope_data.get("branch", "local"),
            path=scope_data.get("path", ""),
            framework=scope_data.get("framework"),
            domain=scope_data.get("domain"),
            route=scope_data.get("route"),
            tags=scope_data.get("tags", []),
        )

        discoveries = [self._row_to_discovery(d) for d in discovery_rows]

        run = LearningRun(
            run_id=run_row["id"],
            tenant_id=run_row["tenant_id"],
            application_id=run_row["application_id"],
            scope=scope,
            trigger_type=LearningTriggerType(run_row["trigger_type"]),
            status=LearningRunStatus(run_row["status"]),
            discoveries=discoveries,
            started_at=run_row["started_at"],
            completed_at=run_row["completed_at"],
        )

        return LearningReport(
            run=run,
            discovered_count=summary_data.get("discovered_count", 0),
            changed_count=summary_data.get("changed_count", 0),
            removed_count=summary_data.get("removed_count", 0),
            unchanged_count=summary_data.get("unchanged_count", 0),
            rejected_count=summary_data.get("rejected_count", 0),
            warnings=summary_data.get("warnings", []),
        )

    @staticmethod
    def _row_to_discovery(row: Any) -> LearningDiscovery:
        source_data = _parse_json(row["source"])
        tags_data = _parse_json(row["proposed_tags"])
        warnings_data = _parse_json(row["warnings"])

        source = CatalogueSource(
            type=source_data.get("type", "file_scan"),
            reference=source_data.get("reference", ""),
            file_path=source_data.get("file_path"),
            symbol_name=source_data.get("symbol_name"),
            commit_id=source_data.get("commit_id"),
            scan_id=source_data.get("scan_id"),
        )

        approval: LearningApproval | None = None
        if row["approved_by"]:
            approval = LearningApproval(
                decision=(
                    LearningApprovalDecision.APPROVED
                    if row["status"] == "approved"
                    else LearningApprovalDecision.REJECTED
                ),
                actor_id=row["approved_by"],
                decided_at=row["approved_at"] or datetime.now(UTC),
                reason=row.get("rejection_reason"),
            )

        return LearningDiscovery(
            discovery_id=row["id"],
            discovery_type=LearningDiscoveryType(row["discovery_type"]),
            status=LearningDiscoveryStatus(row["status"]),
            delta=LearningDelta(
                state=LearningDeltaState(row["delta_state"]),
                current_hash=row["content_hash"],
            ),
            summary=row["summary"],
            confidence=row["confidence"],
            source=source,
            proposed_tags=tags_data if isinstance(tags_data, dict) else {},
            approval=approval,
            warnings=warnings_data if isinstance(warnings_data, list) else [],
        )


def _parse_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value or {}
