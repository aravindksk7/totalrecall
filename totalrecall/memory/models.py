from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from totalrecall.contracts import ContractModel


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"
    TOMBSTONED = "tombstoned"
    DEPRECATED = "deprecated"


class MemoryHealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class MemorySource(ContractModel):
    source_type: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    file_path: str | None = None
    symbol_name: str | None = None
    commit_id: str | None = None
    scan_id: str | None = None
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MemoryEntry(ContractModel):
    entity_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    application_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    knowledge: str = Field(min_length=1)
    tags: dict[str, Any] = Field(default_factory=dict)
    source: MemorySource | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: MemoryStatus = MemoryStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MemorySearchRequest(ContractModel):
    tenant_id: str = Field(min_length=1)
    application_id: str = Field(min_length=1)
    query: str = ""
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=10, ge=1, le=100)


class MemorySearchResult(ContractModel):
    items: list[MemoryEntry]
    adapter_version: str = Field(min_length=1)


class MemoryGetRequest(ContractModel):
    tenant_id: str = Field(min_length=1)
    application_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)


class MemoryUpsertRequest(ContractModel):
    memory: MemoryEntry


class MemoryDeleteRequest(ContractModel):
    tenant_id: str = Field(min_length=1)
    application_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    deleted_by: str = Field(min_length=1)
    reason: str | None = None


class MemoryDeleteResult(ContractModel):
    entity_id: str = Field(min_length=1)
    deleted: bool
    adapter_version: str = Field(min_length=1)


class MemoryHealth(ContractModel):
    status: MemoryHealthStatus
    adapter_version: str = Field(min_length=1)
    degraded: bool = False


class MemoryCapabilities(ContractModel):
    adapter_version: str = Field(min_length=1)
    supports_search: bool = True
    supports_get: bool = True
    supports_upsert: bool = True
    supports_delete: bool = True
    supports_shadow_read: bool = False
