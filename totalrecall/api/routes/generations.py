from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from totalrecall.api.dependencies import (
    get_optional_audit_repo,
    get_optional_context_snapshot_repo,
    get_tenant_context,
)
from totalrecall.ratelimit.provider import RateLimitProvider
from totalrecall.auth.models import TenantContext
from totalrecall.generation.models import GenerationRequest, GenerationResult, GenerationStatus
from totalrecall.generation.orchestrator import GenerationOrchestrator
from totalrecall.observability.metrics import GenerationMetrics
from totalrecall.storage.audit_repo import PostgresAuditRepository
from totalrecall.storage.context_repo import PostgresContextSnapshotRepository

router = APIRouter(tags=["generations"])


def get_generation_orchestrator(request: Request) -> GenerationOrchestrator:
    return request.app.state.generation_orchestrator


def _check_rate_limit(request: Request, context: TenantContext) -> None:
    provider: RateLimitProvider | None = getattr(request.app.state, "rate_limit_provider", None)
    if provider is None:
        return
    result = provider.check(context.tenant_id)
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Retry after {result.retry_after_seconds}s.",
            headers={"Retry-After": str(result.retry_after_seconds)},
        )


@router.post(
    "/generations",
    response_model=GenerationResult,
    status_code=status.HTTP_200_OK,
)
def create_generation(
    request: Request,
    body: GenerationRequest,
    background_tasks: BackgroundTasks,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    orchestrator: Annotated[GenerationOrchestrator, Depends(get_generation_orchestrator)],
    audit_repo: Annotated[PostgresAuditRepository | None, Depends(get_optional_audit_repo)] = None,
    context_snapshot_repo: Annotated[
        PostgresContextSnapshotRepository | None,
        Depends(get_optional_context_snapshot_repo),
    ] = None,
) -> GenerationResult:
    _check_rate_limit(request, context)
    if body.tenant_id != context.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request tenant_id does not match authenticated tenant.",
        )
    result = orchestrator.generate(body)
    if audit_repo is not None:
        background_tasks.add_task(
            audit_repo.record,
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
            event_type="generation.completed" if result.status.value == "completed" else "generation.failed",
            subject_type="generation",
            subject_id=body.application_id,
            details={
                "application_id": body.application_id,
                "status": result.status.value,
                "artifact_count": len(result.artifacts),
            },
        )
    if context_snapshot_repo is not None and result.context.context_plan_id:
        background_tasks.add_task(
            context_snapshot_repo.save,
            snapshot_id=result.context.context_plan_id,
            tenant_id=context.tenant_id,
            application_id=body.application_id,
            request_id=result.request_id,
            skill_ids=result.context.skill_ids,
            memory_ids=result.context.memory_ids,
            estimated_input_tokens=result.context.estimated_input_tokens,
        )

    m: GenerationMetrics | None = getattr(request.app.state, "metrics", None)
    if m is not None:
        m.record_generation(
            completed=result.status == GenerationStatus.COMPLETED,
            input_tokens=result.context.estimated_input_tokens,
        )
        m.record_validation(status=result.validation.status.value)

    return result
