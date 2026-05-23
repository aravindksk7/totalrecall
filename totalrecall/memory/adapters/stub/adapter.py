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
    MemoryStatus,
    MemoryUpsertRequest,
)


class StubMemoryAdapter:
    adapter_version = "stub"

    def __init__(self, entries: list[MemoryEntry] | None = None) -> None:
        self._entries = {entry.entity_id: entry for entry in entries or []}

    def search(self, request: MemorySearchRequest) -> MemorySearchResult:
        matches = [
            entry
            for entry in self._entries.values()
            if entry.tenant_id == request.tenant_id
            and entry.application_id == request.application_id
            and entry.status == MemoryStatus.ACTIVE
            and self._matches_filters(entry, request.filters)
        ]
        return MemorySearchResult(
            items=matches[: request.limit],
            adapter_version=self.adapter_version,
        )

    def get(self, request: MemoryGetRequest) -> MemoryEntry | None:
        entry = self._entries.get(request.entity_id)
        if (
            entry
            and entry.tenant_id == request.tenant_id
            and entry.application_id == request.application_id
            and entry.status == MemoryStatus.ACTIVE
        ):
            return entry
        return None

    def upsert(self, request: MemoryUpsertRequest) -> MemoryEntry:
        self._entries[request.memory.entity_id] = request.memory
        return request.memory

    def delete(self, request: MemoryDeleteRequest) -> MemoryDeleteResult:
        entry = self._entries.get(request.entity_id)
        deleted = False
        if (
            entry
            and entry.tenant_id == request.tenant_id
            and entry.application_id == request.application_id
        ):
            self._entries[request.entity_id] = entry.model_copy(
                update={"status": MemoryStatus.DELETED}
            )
            deleted = True
        return MemoryDeleteResult(
            entity_id=request.entity_id,
            deleted=deleted,
            adapter_version=self.adapter_version,
        )

    def health(self) -> MemoryHealth:
        return MemoryHealth(status=MemoryHealthStatus.OK, adapter_version=self.adapter_version)

    def capabilities(self) -> MemoryCapabilities:
        return MemoryCapabilities(adapter_version=self.adapter_version, supports_shadow_read=True)

    @staticmethod
    def _matches_filters(entry: MemoryEntry, filters: dict[str, object]) -> bool:
        for key, value in filters.items():
            if entry.tags.get(key) != value:
                return False
        return True
