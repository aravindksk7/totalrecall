from typing import Protocol

from totalrecall.memory.models import (
    MemoryCapabilities,
    MemoryDeleteRequest,
    MemoryDeleteResult,
    MemoryEntry,
    MemoryGetRequest,
    MemoryHealth,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryUpsertRequest,
)


class MemoryAdapter(Protocol):
    adapter_version: str

    def search(self, request: MemorySearchRequest) -> MemorySearchResult:
        ...

    def get(self, request: MemoryGetRequest) -> MemoryEntry | None:
        ...

    def upsert(self, request: MemoryUpsertRequest) -> MemoryEntry:
        ...

    def delete(self, request: MemoryDeleteRequest) -> MemoryDeleteResult:
        ...

    def health(self) -> MemoryHealth:
        ...

    def capabilities(self) -> MemoryCapabilities:
        ...
