"""Skills API: list loaded skills and manage governance (promote/deprecate)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status as http_status
from pydantic import BaseModel

from totalrecall.api.dependencies import get_tenant_context
from totalrecall.auth.models import TenantContext
from totalrecall.auth.permissions import PUBLISH_SKILL, has_permission
from totalrecall.skills.models import SkillStatus
from totalrecall.skills.registry import SkillNotFoundError, SkillRegistry
from totalrecall.storage.skill_governance_repo import PostgresSkillGovernanceRepository

router = APIRouter(tags=["skills"])


def _get_skill_registry(request: Request) -> SkillRegistry:
    return request.app.state.skill_registry


def _get_optional_governance_repo(
    request: Request,
) -> PostgresSkillGovernanceRepository | None:
    return getattr(request.app.state, "skill_governance_repo", None)


class SkillSummary(BaseModel):
    skill_id: str
    version: str
    language: str
    framework: str
    status: str


class SkillListResponse(BaseModel):
    skills: list[SkillSummary]
    total: int


class GovernanceRequest(BaseModel):
    notes: str | None = None


class GovernanceResponse(BaseModel):
    skill_id: str
    version: str
    status: str
    promoted_by: str


@router.get("/skills", response_model=SkillListResponse)
def list_skills(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    registry: Annotated[SkillRegistry, Depends(_get_skill_registry)],
) -> SkillListResponse:
    summaries = [
        SkillSummary(
            skill_id=s.skill_id,
            version=s.version,
            language=s.language,
            framework=s.framework,
            status=registry._effective_status(s),
        )
        for s in registry.all()
    ]
    return SkillListResponse(skills=summaries, total=len(summaries))


@router.post("/skills/{skill_id}/promote", response_model=GovernanceResponse)
async def promote_skill(
    skill_id: str,
    body: GovernanceRequest,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    registry: Annotated[SkillRegistry, Depends(_get_skill_registry)],
    governance_repo: Annotated[
        PostgresSkillGovernanceRepository | None,
        Depends(_get_optional_governance_repo),
    ] = None,
) -> GovernanceResponse:
    if not has_permission(context.roles, PUBLISH_SKILL):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions: skill:publish required.",
        )
    try:
        skill = registry.get(skill_id)
    except SkillNotFoundError:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_id}' not found.",
        )

    new_overrides = {**registry._governance_overrides, skill_id: SkillStatus.ACTIVE}
    registry.apply_governance_overrides(new_overrides)

    if governance_repo is not None:
        await governance_repo.upsert(
            skill_id=skill_id,
            version=skill.version,
            status="active",
            promoted_by=context.actor_id,
            notes=body.notes,
        )

    return GovernanceResponse(
        skill_id=skill_id,
        version=skill.version,
        status="active",
        promoted_by=context.actor_id,
    )


@router.post("/skills/{skill_id}/deprecate", response_model=GovernanceResponse)
async def deprecate_skill(
    skill_id: str,
    body: GovernanceRequest,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    registry: Annotated[SkillRegistry, Depends(_get_skill_registry)],
    governance_repo: Annotated[
        PostgresSkillGovernanceRepository | None,
        Depends(_get_optional_governance_repo),
    ] = None,
) -> GovernanceResponse:
    if not has_permission(context.roles, PUBLISH_SKILL):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions: skill:publish required.",
        )
    try:
        skill = registry.get(skill_id)
    except SkillNotFoundError:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_id}' not found.",
        )

    new_overrides = {**registry._governance_overrides, skill_id: SkillStatus.DEPRECATED}
    registry.apply_governance_overrides(new_overrides)

    if governance_repo is not None:
        await governance_repo.upsert(
            skill_id=skill_id,
            version=skill.version,
            status="deprecated",
            promoted_by=context.actor_id,
            notes=body.notes,
        )

    return GovernanceResponse(
        skill_id=skill_id,
        version=skill.version,
        status="deprecated",
        promoted_by=context.actor_id,
    )
