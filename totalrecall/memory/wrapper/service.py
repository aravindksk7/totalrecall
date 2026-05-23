from totalrecall.cache.provider import TTLCache, build_search_cache_key
from totalrecall.config.feature_flags import FeatureFlagProvider
from totalrecall.memory.adapters.base import MemoryAdapter
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
from totalrecall.memory.tombstone import TombstoneFilter


class MemoryWrapper:
    def __init__(
        self,
        feature_flags: FeatureFlagProvider,
        adapters: dict[str, MemoryAdapter],
        tombstone_filter: TombstoneFilter | None = None,
        cache: TTLCache | None = None,
    ) -> None:
        self._feature_flags = feature_flags
        self._adapters = adapters
        self._tombstone_filter = tombstone_filter or TombstoneFilter()
        self._cache = cache
        # Populated during shadow reads; keyed log entries for test observability.
        self._shadow_log: list[dict] = []

    def search(self, request: MemorySearchRequest) -> MemorySearchResult:
        if self._cache is not None:
            cache_key = build_search_cache_key(
                request.tenant_id,
                request.application_id,
                request.query or "",
                request.filters,
                request.limit,
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        primary_result = self._active_adapter().search(request)

        # Shadow read: call a secondary adapter for comparison without changing the result.
        shadow_name = self._feature_flags.get_string("memory.shadow_adapter", "")
        active_name = self._active_adapter_name()
        if shadow_name and shadow_name != active_name:
            shadow_adapter = self._adapters.get(shadow_name)
            if shadow_adapter is not None:
                try:
                    shadow_result = shadow_adapter.search(request)
                    primary_ids = {e.entity_id for e in primary_result.items}
                    shadow_ids = {e.entity_id for e in shadow_result.items}
                    self._shadow_log.append({
                        "primary_adapter": primary_result.adapter_version,
                        "shadow_adapter": shadow_result.adapter_version,
                        "primary_count": len(primary_result.items),
                        "shadow_count": len(shadow_result.items),
                        "discrepancy": primary_ids != shadow_ids,
                    })
                except Exception as exc:
                    self._shadow_log.append({
                        "primary_adapter": primary_result.adapter_version,
                        "shadow_adapter": shadow_name,
                        "error": str(exc),
                        "discrepancy": True,
                    })

        filtered = self._tombstone_filter.filter_entries(primary_result.items)
        search_result = MemorySearchResult(
            items=filtered,
            adapter_version=primary_result.adapter_version,
        )

        if self._cache is not None:
            self._cache.set(cache_key, search_result)  # type: ignore[possibly-undefined]

        return search_result

    def get(self, request: MemoryGetRequest) -> MemoryEntry | None:
        if self._tombstone_filter.is_tombstoned(
            request.tenant_id, request.application_id, request.entity_id
        ):
            return None
        return self._active_adapter().get(request)

    def upsert(self, request: MemoryUpsertRequest) -> MemoryEntry:
        return self._active_adapter().upsert(request)

    def delete(self, request: MemoryDeleteRequest) -> MemoryDeleteResult:
        return self._active_adapter().delete(request)

    def health(self) -> MemoryHealth:
        return self._active_adapter().health()

    def capabilities(self) -> MemoryCapabilities:
        return self._active_adapter().capabilities()

    def _active_adapter_name(self) -> str:
        return self._feature_flags.get_string("memory.adapter", "null")

    def _active_adapter(self) -> MemoryAdapter:
        adapter_name = self._active_adapter_name()
        adapter = self._adapters.get(adapter_name)
        if adapter is None:
            adapter = self._adapters["null"]
        return adapter
