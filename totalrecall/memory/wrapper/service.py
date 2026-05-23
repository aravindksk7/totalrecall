import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

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


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class _MemoryOperationMetrics:
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _totals: dict[str, int] = field(default_factory=dict)
    _successes: dict[str, int] = field(default_factory=dict)
    _failures: dict[str, int] = field(default_factory=dict)
    _latency_totals_ms: dict[str, float] = field(default_factory=dict)
    search_cache_hit_total: int = 0
    last_success_at: str | None = None
    last_failure_at: str | None = None
    last_error_type: str | None = None

    def record_success(
        self,
        operation: str,
        latency_ms: float,
        *,
        cache_hit: bool = False,
    ) -> None:
        with self._lock:
            self._totals[operation] = self._totals.get(operation, 0) + 1
            self._successes[operation] = self._successes.get(operation, 0) + 1
            self._latency_totals_ms[operation] = (
                self._latency_totals_ms.get(operation, 0.0) + latency_ms
            )
            if cache_hit:
                self.search_cache_hit_total += 1
            self.last_success_at = _now_iso()

    def record_failure(self, operation: str, latency_ms: float, exc: Exception) -> None:
        with self._lock:
            self._totals[operation] = self._totals.get(operation, 0) + 1
            self._failures[operation] = self._failures.get(operation, 0) + 1
            self._latency_totals_ms[operation] = (
                self._latency_totals_ms.get(operation, 0.0) + latency_ms
            )
            self.last_failure_at = _now_iso()
            self.last_error_type = type(exc).__name__

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            operations = ("search", "get", "upsert", "delete")
            payload: dict[str, Any] = {
                "search_cache_hit_total": self.search_cache_hit_total,
                "last_success_at": self.last_success_at,
                "last_failure_at": self.last_failure_at,
                "last_error_type": self.last_error_type,
            }
            for operation in operations:
                total = self._totals.get(operation, 0)
                success = self._successes.get(operation, 0)
                latency_total = self._latency_totals_ms.get(operation, 0.0)
                payload[f"{operation}_total"] = total
                payload[f"{operation}_success_total"] = success
                payload[f"{operation}_failure_total"] = self._failures.get(operation, 0)
                payload[f"average_{operation}_latency_ms"] = (
                    round(latency_total / success, 2) if success else 0.0
                )
            return payload


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
        self._operation_metrics = _MemoryOperationMetrics()

    def search(self, request: MemorySearchRequest) -> MemorySearchResult:
        started = time.perf_counter()
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
                self._operation_metrics.record_success(
                    "search",
                    (time.perf_counter() - started) * 1000,
                    cache_hit=True,
                )
                return cached

        try:
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

            self._operation_metrics.record_success(
                "search",
                (time.perf_counter() - started) * 1000,
            )
            return search_result
        except Exception as exc:
            self._operation_metrics.record_failure(
                "search",
                (time.perf_counter() - started) * 1000,
                exc,
            )
            raise

    def get(self, request: MemoryGetRequest) -> MemoryEntry | None:
        started = time.perf_counter()
        try:
            if self._tombstone_filter.is_tombstoned(
                request.tenant_id, request.application_id, request.entity_id
            ):
                result = None
            else:
                result = self._active_adapter().get(request)
            self._operation_metrics.record_success(
                "get",
                (time.perf_counter() - started) * 1000,
            )
            return result
        except Exception as exc:
            self._operation_metrics.record_failure(
                "get",
                (time.perf_counter() - started) * 1000,
                exc,
            )
            raise

    def upsert(self, request: MemoryUpsertRequest) -> MemoryEntry:
        started = time.perf_counter()
        try:
            result = self._active_adapter().upsert(request)
            self._operation_metrics.record_success(
                "upsert",
                (time.perf_counter() - started) * 1000,
            )
            return result
        except Exception as exc:
            self._operation_metrics.record_failure(
                "upsert",
                (time.perf_counter() - started) * 1000,
                exc,
            )
            raise

    def delete(self, request: MemoryDeleteRequest) -> MemoryDeleteResult:
        started = time.perf_counter()
        try:
            result = self._active_adapter().delete(request)
            self._operation_metrics.record_success(
                "delete",
                (time.perf_counter() - started) * 1000,
            )
            return result
        except Exception as exc:
            self._operation_metrics.record_failure(
                "delete",
                (time.perf_counter() - started) * 1000,
                exc,
            )
            raise

    def health(self) -> MemoryHealth:
        return self._active_adapter().health()

    def capabilities(self) -> MemoryCapabilities:
        return self._active_adapter().capabilities()

    def active_adapter_name(self) -> str:
        return self._active_adapter_name()

    def operation_stats(self) -> dict[str, Any]:
        return self._operation_metrics.snapshot()

    def _active_adapter_name(self) -> str:
        return self._feature_flags.get_string("memory.adapter", "null")

    def _active_adapter(self) -> MemoryAdapter:
        adapter_name = self._active_adapter_name()
        adapter = self._adapters.get(adapter_name)
        if adapter is None:
            adapter = self._adapters["null"]
        return adapter
