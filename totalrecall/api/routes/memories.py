from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status

from totalrecall.api.dependencies import (
    get_audit_repo,
    get_tenant_context,
    get_tombstone_filter,
    get_tombstone_repo,
)
from totalrecall.cache.provider import search_invalidation_prefix
from totalrecall.auth.models import TenantContext
from totalrecall.auth.permissions import has_permission
from totalrecall.contracts import ContractModel
from totalrecall.memory.tombstone import TombstoneFilter
from totalrecall.memory.wrapper.service import MemoryWrapper
from totalrecall.storage.audit_repo import PostgresAuditRepository
from totalrecall.storage.tombstone_repo import PostgresTombstoneRepository

router = APIRouter(tags=["memories"])


class MemoryDeleteBody(ContractModel):
    application_id: str
    reason: str | None = None


class MemoryDeleteResponse(ContractModel):
    entity_id: str
    deleted: bool
    tombstoned: bool


def _get_memory_wrapper(request: object) -> MemoryWrapper:
    return request.app.state.memory_wrapper  # type: ignore[union-attr]


@router.delete("/memories/{entity_id}", response_model=MemoryDeleteResponse)
async def delete_memory(
    request: Request,
    entity_id: str,
    body: Annotated[MemoryDeleteBody, Body()],
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    tombstone_filter: Annotated[TombstoneFilter, Depends(get_tombstone_filter)],
    tombstone_repo: Annotated[PostgresTombstoneRepository, Depends(get_tombstone_repo)],
    audit_repo: Annotated[PostgresAuditRepository, Depends(get_audit_repo)],
) -> MemoryDeleteResponse:
    if not has_permission(context.roles, "memory:delete"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission 'memory:delete' required.",
        )

    # Write tombstone to Postgres
    await tombstone_repo.add(
        tenant_id=context.tenant_id,
        application_id=body.application_id,
        entity_id=entity_id,
        deleted_by=context.actor_id,
        reason=body.reason,
    )

    # Update in-memory filter so subsequent requests see the deletion immediately
    tombstone_filter.add(context.tenant_id, body.application_id, entity_id)

    # Record audit event
    await audit_repo.record(
        tenant_id=context.tenant_id,
        actor_id=context.actor_id,
        event_type="memory.deleted",
        subject_type="memory",
        subject_id=entity_id,
        details={"application_id": body.application_id, "reason": body.reason},
    )

    # Invalidate memory search cache so next context plan excludes the deleted memory
    cache = getattr(request.app.state, "cache", None)
    if cache is not None:
        cache.invalidate_prefix(
            search_invalidation_prefix(context.tenant_id, body.application_id)
        )

    return MemoryDeleteResponse(entity_id=entity_id, deleted=True, tombstoned=True)
