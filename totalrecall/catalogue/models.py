from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from totalrecall.contracts import ContractModel
from totalrecall.generation.models import Framework


class CatalogueCategory(StrEnum):
    STATIC_SKILL = "static_skill"
    DYNAMIC_MEMORY = "dynamic_memory"
    LEARNING_REFERENCE = "learning_reference"


class CatalogueStatus(StrEnum):
    DISCOVERED = "discovered"
    ACTIVE = "active"
    REJECTED = "rejected"
    TOMBSTONED = "tombstoned"
    DEPRECATED = "deprecated"


class CatalogueSource(ContractModel):
    type: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    file_path: str | None = None
    symbol_name: str | None = None
    commit_id: str | None = None
    scan_id: str | None = None


class CatalogueEntry(ContractModel):
    entity_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    application_id: str = Field(min_length=1)
    category: CatalogueCategory
    status: CatalogueStatus
    summary: str = Field(min_length=1)
    tags: dict[str, Any] = Field(default_factory=dict)
    source: CatalogueSource | None = None
    owner: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    deleted_by: str | None = None
    deleted_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CatalogueSearchFilters(ContractModel):
    tenant_id: str = Field(min_length=1)
    application_id: str | None = None
    category: CatalogueCategory | None = None
    status: CatalogueStatus | None = None
    domain: str | None = None
    framework: Framework | None = None
    route: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class CatalogueSearchResult(ContractModel):
    items: list[CatalogueEntry]
    total: int = Field(ge=0)
