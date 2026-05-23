"""Learning run API routes."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from totalrecall.api.dependencies import get_audit_repo, get_catalogue_repo, get_learning_repo, get_tenant_context
from totalrecall.auth.models import TenantContext
from totalrecall.auth.permissions import has_permission
from totalrecall.catalogue.models import CatalogueEntry
from totalrecall.contracts import ContractModel
from totalrecall.learning.models import (
    LearningReport,
    LearningScope,
    LearningTriggerType,
)
from totalrecall.learning.promotion import discovery_to_entry, should_promote
from totalrecall.learning.runner import run_learning
from totalrecall.storage.audit_repo import PostgresAuditRepository
from totalrecall.storage.catalogue_repo import PostgresCatalogueRepository
from totalrecall.storage.learning_repo import PostgresLearningRepository

router = APIRouter(tags=["learning"])


class TriggerRunBody(ContractModel):
    application_id: str
    scope: LearningScope
    trigger_type: LearningTriggerType = LearningTriggerType.MANUAL


class ApproveDiscoveryBody(ContractModel):
    reason: str | None = None


class RejectDiscoveryBody(ContractModel):
    reason: str | None = None


@router.post("/learning/runs", response_model=LearningReport, status_code=status.HTTP_201_CREATED)
async def trigger_learning_run(
    body: Annotated[TriggerRunBody, Body()],
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    repo: Annotated[PostgresLearningRepository, Depends(get_learning_repo)],
    audit_repo: Annotated[PostgresAuditRepository, Depends(get_audit_repo)],
) -> LearningReport:
    if not has_permission(context.roles, "learning:promote"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission 'learning:promote' required.",
        )

    previous_hashes = await repo.get_previous_hashes(context.tenant_id, body.application_id)
    report = run_learning(
        tenant_id=context.tenant_id,
        application_id=body.application_id,
        scope=body.scope,
        previous_hashes=previous_hashes,
        trigger_type=body.trigger_type,
    )
    await repo.save_report(report)

    await audit_repo.record(
        tenant_id=context.tenant_id,
        actor_id=context.actor_id,
        event_type="learning.run.triggered",
        subject_type="learning_run",
        subject_id=report.run.run_id,
        details={
            "application_id": body.application_id,
            "scope_path": body.scope.path,
            "discovered_count": report.discovered_count,
            "trigger_type": body.trigger_type.value,
        },
    )

    return report


@router.get("/learning/runs", response_model=list[LearningReport])
async def list_learning_runs(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    repo: Annotated[PostgresLearningRepository, Depends(get_learning_repo)],
    application_id: str | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=20, ge=1, le=100),  # noqa: B008
) -> list[LearningReport]:
    return await repo.list_runs(context.tenant_id, application_id=application_id, limit=limit)


@router.get("/learning/runs/{run_id}", response_model=LearningReport)
async def get_learning_run(
    run_id: str,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    repo: Annotated[PostgresLearningRepository, Depends(get_learning_repo)],
) -> LearningReport:
    report = await repo.get_run(context.tenant_id, run_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning run '{run_id}' not found.",
        )
    return report


@router.post("/learning/runs/{run_id}/approve/{discovery_id}", status_code=status.HTTP_200_OK)
async def approve_discovery(
    run_id: str,
    discovery_id: str,
    body: Annotated[ApproveDiscoveryBody, Body()],
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    repo: Annotated[PostgresLearningRepository, Depends(get_learning_repo)],
    catalogue_repo: Annotated[PostgresCatalogueRepository, Depends(get_catalogue_repo)],
    audit_repo: Annotated[PostgresAuditRepository, Depends(get_audit_repo)],
) -> dict:
    if not has_permission(context.roles, "learning:promote"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission 'learning:promote' required.",
        )

    updated = await repo.approve_discovery(
        context.tenant_id, discovery_id, context.actor_id, body.reason
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Discovery '{discovery_id}' not found or already processed.",
        )

    promoted = False
    discovery_result = await repo.get_discovery(context.tenant_id, discovery_id)
    if discovery_result is not None:
        discovery, application_id = discovery_result
        if should_promote(discovery):
            entry: CatalogueEntry = discovery_to_entry(
                discovery, context.tenant_id, application_id, context.actor_id
            )
            await catalogue_repo.upsert(entry)
            promoted = True

    await audit_repo.record(
        tenant_id=context.tenant_id,
        actor_id=context.actor_id,
        event_type="learning.discovery.approved",
        subject_type="learning_discovery",
        subject_id=discovery_id,
        details={"run_id": run_id, "reason": body.reason, "promoted": promoted},
    )

    return {"discovery_id": discovery_id, "approved": True, "promoted": promoted}


@router.post("/learning/runs/{run_id}/reject/{discovery_id}", status_code=status.HTTP_200_OK)
async def reject_discovery(
    run_id: str,
    discovery_id: str,
    body: Annotated[RejectDiscoveryBody, Body()],
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    repo: Annotated[PostgresLearningRepository, Depends(get_learning_repo)],
    audit_repo: Annotated[PostgresAuditRepository, Depends(get_audit_repo)],
) -> dict:
    if not has_permission(context.roles, "learning:promote"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission 'learning:promote' required.",
        )

    updated = await repo.reject_discovery(
        context.tenant_id, discovery_id, context.actor_id, body.reason
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Discovery '{discovery_id}' not found or already processed.",
        )

    await audit_repo.record(
        tenant_id=context.tenant_id,
        actor_id=context.actor_id,
        event_type="learning.discovery.rejected",
        subject_type="learning_discovery",
        subject_id=discovery_id,
        details={"run_id": run_id, "reason": body.reason},
    )

    return {"discovery_id": discovery_id, "rejected": True}
