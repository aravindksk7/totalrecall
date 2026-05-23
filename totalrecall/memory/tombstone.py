"""In-process tombstone filter: excludes deleted/tombstoned memories from search and get results.

The filter is populated on startup from the Postgres memory_tombstones table and updated
immediately on every delete call, so deletions take effect for all subsequent requests
without a database round-trip per search.
"""

from totalrecall.memory.models import MemoryEntry


class TombstoneFilter:
    """Thread-safe in-memory set of tombstoned (tenant_id, application_id, entity_id) triples.

    Designed to be a singleton held in app.state and shared across requests.
    """

    def __init__(self) -> None:
        self._tombstones: set[tuple[str, str, str]] = set()

    def add(self, tenant_id: str, application_id: str, entity_id: str) -> None:
        self._tombstones.add((tenant_id, application_id, entity_id))

    def remove(self, tenant_id: str, application_id: str, entity_id: str) -> None:
        self._tombstones.discard((tenant_id, application_id, entity_id))

    def is_tombstoned(self, tenant_id: str, application_id: str, entity_id: str) -> bool:
        return (tenant_id, application_id, entity_id) in self._tombstones

    def filter_entries(self, entries: list[MemoryEntry]) -> list[MemoryEntry]:
        return [
            e
            for e in entries
            if not self.is_tombstoned(e.tenant_id, e.application_id, e.entity_id)
        ]

    def load_bulk(self, tombstones: list[tuple[str, str, str]]) -> None:
        """Bulk-load tombstones from Postgres on startup."""
        self._tombstones.update(tombstones)

    @property
    def count(self) -> int:
        return len(self._tombstones)
