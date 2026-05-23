from enum import StrEnum
from typing import Any

from pydantic import Field

from totalrecall.contracts import ContractModel
from totalrecall.testgen.jira.models import JiraStory


class ContextExclusionReason(StrEnum):
    DOMAIN_MISMATCH = "domain_mismatch"
    ROUTE_MISMATCH = "route_mismatch"
    FRAMEWORK_MISMATCH = "framework_mismatch"
    TOMBSTONED = "tombstoned"
    TOKEN_BUDGET = "token_budget"
    POLICY = "policy"


class ContextExclusion(ContractModel):
    entity_id: str = Field(min_length=1)
    reason: ContextExclusionReason
    details: dict[str, Any] = Field(default_factory=dict)


class TokenBudget(ContractModel):
    max_input_tokens: int = Field(ge=1)
    estimated_input_tokens: int = Field(default=0, ge=0)
    baseline_estimate: int = Field(default=0, ge=0)
    estimated_tokens_saved: int = Field(default=0, ge=0)


class SelectedSkill(ContractModel):
    skill_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    reason: str | None = None


class SelectedMemory(ContractModel):
    memory_id: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str | None = None


class ContextPlan(ContractModel):
    context_plan_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    application_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    selected_skills: list[SelectedSkill] = Field(default_factory=list)
    selected_memories: list[SelectedMemory] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    memory_ids: list[str] = Field(default_factory=list)
    excluded: list[ContextExclusion] = Field(default_factory=list)
    token_budget: TokenBudget
    feature_flags: dict[str, Any] = Field(default_factory=dict)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    jira_story: JiraStory | None = Field(default=None)
    rag_chunks: list[Any] = Field(default_factory=list)
