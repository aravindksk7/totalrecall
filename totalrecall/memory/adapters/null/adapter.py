from totalrecall.memory.models import (
    MemoryCapabilities,
    MemoryDeleteRequest,
    MemoryDeleteResult,
    MemoryEntry,
    MemoryGetRequest,
    MemoryHealth,
    MemoryHealthStatus,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryUpsertRequest,
)


class NullMemoryAdapter:
    adapter_version = "null"

    def search(self, request: MemorySearchRequest) -> MemorySearchResult:
        return MemorySearchResult(items=[], adapter_version=self.adapter_version)

    def get(self, request: MemoryGetRequest) -> MemoryEntry | None:
        return None

    def upsert(self, request: MemoryUpsertRequest) -> MemoryEntry:
        return request.memory

    def delete(self, request: MemoryDeleteRequest) -> MemoryDeleteResult:
        return MemoryDeleteResult(
            entity_id=request.entity_id,
            deleted=False,
            adapter_version=self.adapter_version,
        )

    def health(self) -> MemoryHealth:
        return MemoryHealth(
            status=MemoryHealthStatus.DEGRADED,
            adapter_version=self.adapter_version,
            degraded=True,
        )

    def capabilities(self) -> MemoryCapabilities:
        return MemoryCapabilities(
            adapter_version=self.adapter_version,
            supports_upsert=False,
            supports_delete=False,
        )
