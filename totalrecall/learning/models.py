from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from totalrecall.catalogue.models import CatalogueSource
from totalrecall.contracts import ContractModel
from totalrecall.generation.models import Framework


class LearningTriggerType(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    EVENT = "event"


class LearningRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class LearningDiscoveryType(StrEnum):
    STATIC_SKILL_CANDIDATE = "static_skill_candidate"
    DYNAMIC_MEMORY = "dynamic_memory"
    CATALOGUE_REFERENCE = "catalogue_reference"


class LearningDiscoveryStatus(StrEnum):
    DISCOVERED = "discovered"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROMOTED = "promoted"


class LearningDeltaState(StrEnum):
    NEW = "new"
    CHANGED = "changed"
    REMOVED = "removed"
    UNCHANGED = "unchanged"


class LearningApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class LearningScope(ContractModel):
    repository: str = Field(min_length=1)
    branch: str = Field(min_length=1)
    path: str = Field(min_length=1)
    framework: Framework | None = None
    domain: str | None = None
    route: str | None = None
    tags: list[str] = Field(default_factory=list)


class LearningApproval(ContractModel):
    decision: LearningApprovalDecision
    actor_id: str = Field(min_length=1)
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reason: str | None = None


class LearningDelta(ContractModel):
    state: LearningDeltaState
    previous_hash: str | None = None
    current_hash: str | None = None
    changed_fields: list[str] = Field(default_factory=list)


class LearningDiscovery(ContractModel):
    discovery_id: str = Field(min_length=1)
    discovery_type: LearningDiscoveryType
    status: LearningDiscoveryStatus = LearningDiscoveryStatus.DISCOVERED
    delta: LearningDelta
    summary: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: CatalogueSource
    proposed_tags: dict[str, Any] = Field(default_factory=dict)
    approval: LearningApproval | None = None
    warnings: list[str] = Field(default_factory=list)


class LearningRun(ContractModel):
    run_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    application_id: str = Field(min_length=1)
    scope: LearningScope
    trigger_type: LearningTriggerType
    status: LearningRunStatus = LearningRunStatus.QUEUED
    discoveries: list[LearningDiscovery] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class LearningReport(ContractModel):
    run: LearningRun
    discovered_count: int = Field(ge=0)
    changed_count: int = Field(ge=0)
    removed_count: int = Field(ge=0)
    unchanged_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class DiscoverySearchResult(ContractModel):
    discovery_id: str
    run_id: str
    application_id: str
    discovery_type: LearningDiscoveryType
    status: LearningDiscoveryStatus
    summary: str
    confidence: float
    delta_state: LearningDeltaState
    warnings: list[str] = Field(default_factory=list)
    approval: LearningApproval | None = None


class BulkDecisionResult(ContractModel):
    processed: int
    skipped: int
    discovery_ids: list[str] = Field(default_factory=list)
