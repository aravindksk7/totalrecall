"""Unit tests: adapter version switching, shadow reads, and rollback."""

from totalrecall.config.feature_flags import ConfigFeatureFlagProvider
from totalrecall.memory.adapters.null import NullMemoryAdapter
from totalrecall.memory.adapters.stub import StubMemoryAdapter
from totalrecall.memory.models import (
    MemoryEntry,
    MemorySearchRequest,
    MemoryUpsertRequest,
)
from totalrecall.memory.wrapper.service import MemoryWrapper


def _entry(entity_id: str, adapter_label: str = "a") -> MemoryEntry:
    return MemoryEntry(
        entity_id=entity_id,
        tenant_id="tenant_t",
        application_id="app_t",
        summary=f"Entry {entity_id} from {adapter_label}",
        knowledge=f"Knowledge for {entity_id}",
    )


def _search_request() -> MemorySearchRequest:
    return MemorySearchRequest(tenant_id="tenant_t", application_id="app_t")


def _build_wrapper(
    primary: str = "stub_a",
    shadow: str = "",
    entries_a: list | None = None,
    entries_b: list | None = None,
) -> MemoryWrapper:
    flags: dict = {"memory.adapter": primary}
    if shadow:
        flags["memory.shadow_adapter"] = shadow
    adapters = {
        "stub_a": StubMemoryAdapter(entries_a if entries_a is not None else [_entry("mem_a", "a")]),
        "stub_b": StubMemoryAdapter(entries_b if entries_b is not None else [_entry("mem_b", "b")]),
        "null": NullMemoryAdapter(),
    }
    return MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider(flags),
        adapters=adapters,
    )


# --- adapter version switching ---

def test_primary_adapter_version_is_returned() -> None:
    wrapper = _build_wrapper(primary="stub_a")
    result = wrapper.search(_search_request())
    assert result.adapter_version == "stub"


def test_adapter_switch_changes_result_adapter_version() -> None:
    """Switching the feature flag routes to the new adapter and its version appears in results."""
    wrapper = _build_wrapper(primary="stub_a")
    # Simulate in-process feature-flag update (e.g., runtime flag refresh)
    wrapper._feature_flags._flags["memory.adapter"] = "stub_b"
    result = wrapper.search(_search_request())
    assert result.adapter_version == "stub"  # both stubs share the "stub" version string
    assert result.items[0].entity_id == "mem_b"


def test_adapter_switch_returns_new_adapters_entries() -> None:
    wrapper = _build_wrapper(primary="stub_a", entries_a=[_entry("mem_a")], entries_b=[_entry("mem_b")])
    result_a = wrapper.search(_search_request())
    assert result_a.items[0].entity_id == "mem_a"

    wrapper._feature_flags._flags["memory.adapter"] = "stub_b"
    result_b = wrapper.search(_search_request())
    assert result_b.items[0].entity_id == "mem_b"


# --- rollback ---

def test_rollback_restores_original_adapters_entries() -> None:
    """After switching to stub_b, rolling back to stub_a returns stub_a's entries."""
    wrapper = _build_wrapper(primary="stub_a", entries_a=[_entry("mem_a")], entries_b=[_entry("mem_b")])
    wrapper._feature_flags._flags["memory.adapter"] = "stub_b"
    assert wrapper.search(_search_request()).items[0].entity_id == "mem_b"

    # Rollback
    wrapper._feature_flags._flags["memory.adapter"] = "stub_a"
    result = wrapper.search(_search_request())
    assert result.items[0].entity_id == "mem_a"


def test_rollback_to_unknown_adapter_falls_back_to_null() -> None:
    """Rolling back to an adapter name not in the registry falls back to null (degraded)."""
    wrapper = _build_wrapper(primary="stub_a")
    wrapper._feature_flags._flags["memory.adapter"] = "mem0_vnext"  # not registered
    result = wrapper.search(_search_request())
    assert result.items == []
    assert result.adapter_version == "null"


# --- shadow reads ---

def test_shadow_read_logs_comparison_entry() -> None:
    wrapper = _build_wrapper(primary="stub_a", shadow="stub_b")
    wrapper.search(_search_request())
    assert len(wrapper._shadow_log) == 1


def test_shadow_read_primary_result_is_returned() -> None:
    """Shadow read must not change which adapter's entries are returned."""
    wrapper = _build_wrapper(
        primary="stub_a",
        shadow="stub_b",
        entries_a=[_entry("mem_a")],
        entries_b=[_entry("mem_b")],
    )
    result = wrapper.search(_search_request())
    assert result.items[0].entity_id == "mem_a"
    assert result.adapter_version == "stub"


def test_shadow_read_records_discrepancy_when_results_differ() -> None:
    wrapper = _build_wrapper(
        primary="stub_a",
        shadow="stub_b",
        entries_a=[_entry("mem_a")],
        entries_b=[_entry("mem_b")],
    )
    wrapper.search(_search_request())
    log = wrapper._shadow_log[0]
    assert log["discrepancy"] is True
    assert log["primary_count"] == 1
    assert log["shadow_count"] == 1


def test_shadow_read_records_no_discrepancy_when_results_match() -> None:
    shared_entries = [_entry("mem_shared")]
    wrapper = _build_wrapper(primary="stub_a", shadow="stub_b", entries_a=shared_entries, entries_b=shared_entries)
    wrapper.search(_search_request())
    assert wrapper._shadow_log[0]["discrepancy"] is False


def test_shadow_failure_is_silenced_and_logged() -> None:
    """A crashing shadow adapter must not propagate its exception to the caller."""

    class _BrokenAdapter:
        adapter_version = "broken"

        def search(self, request):  # noqa: ANN001
            raise RuntimeError("shadow adapter down")

    flags = {"memory.adapter": "stub_a", "memory.shadow_adapter": "broken"}
    wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider(flags),
        adapters={
            "stub_a": StubMemoryAdapter([_entry("mem_a")]),
            "broken": _BrokenAdapter(),  # type: ignore[dict-item]
            "null": NullMemoryAdapter(),
        },
    )
    result = wrapper.search(_search_request())
    assert result.items[0].entity_id == "mem_a"
    assert len(wrapper._shadow_log) == 1
    assert "error" in wrapper._shadow_log[0]
    assert wrapper._shadow_log[0]["discrepancy"] is True


def test_shadow_skipped_when_same_as_primary() -> None:
    """No shadow read when the shadow adapter name equals the active adapter."""
    wrapper = _build_wrapper(primary="stub_a", shadow="stub_a")
    wrapper.search(_search_request())
    assert wrapper._shadow_log == []


def test_shadow_skipped_when_not_configured() -> None:
    wrapper = _build_wrapper(primary="stub_a")
    wrapper.search(_search_request())
    assert wrapper._shadow_log == []


def test_shadow_read_not_triggered_for_upsert() -> None:
    """Only search performs shadow reads; upsert goes straight to primary."""
    wrapper = _build_wrapper(primary="stub_a", shadow="stub_b")
    entry = _entry("mem_new")
    wrapper.upsert(MemoryUpsertRequest(memory=entry))
    assert wrapper._shadow_log == []


def test_shadow_read_accumulates_across_multiple_searches() -> None:
    wrapper = _build_wrapper(primary="stub_a", shadow="stub_b")
    wrapper.search(_search_request())
    wrapper.search(_search_request())
    assert len(wrapper._shadow_log) == 2


# --- cache hit ---

def test_search_cache_hit_returns_cached_result_without_adapter_call() -> None:
    from totalrecall.cache.provider import TTLCache, build_search_cache_key
    from totalrecall.memory.models import MemorySearchResult

    cache = TTLCache(ttl_seconds=60)
    req = _search_request()
    cached_result = MemorySearchResult(items=[_entry("cached_entry")], adapter_version="stub")
    cache_key = build_search_cache_key(
        req.tenant_id, req.application_id, req.query or "", req.filters, req.limit
    )
    cache.set(cache_key, cached_result)

    call_count = 0
    real_stub = StubMemoryAdapter([_entry("live_entry")])

    class _CountingAdapter(StubMemoryAdapter):
        def search(self, request):
            nonlocal call_count
            call_count += 1
            return super().search(request)

    wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "counting"}),
        adapters={"counting": _CountingAdapter([_entry("live_entry")]), "null": NullMemoryAdapter()},
        cache=cache,
    )

    result = wrapper.search(req)
    assert result.items[0].entity_id == "cached_entry"
    assert call_count == 0


# --- operation metrics ---

def test_operation_metrics_record_cache_hit_counter() -> None:
    from totalrecall.cache.provider import TTLCache, build_search_cache_key
    from totalrecall.memory.models import MemorySearchResult

    cache = TTLCache(ttl_seconds=60)
    req = _search_request()
    cache_key = build_search_cache_key(
        req.tenant_id, req.application_id, req.query or "", req.filters, req.limit
    )
    cache.set(cache_key, MemorySearchResult(items=[], adapter_version="stub"))

    wrapper = _build_wrapper()
    wrapper._cache = cache  # type: ignore[attr-defined]

    wrapper.search(req)

    stats = wrapper.operation_stats()
    assert stats["search_cache_hit_total"] == 1


# --- tombstone in get ---

def test_get_returns_none_for_tombstoned_entry() -> None:
    from totalrecall.memory.models import MemoryGetRequest
    from totalrecall.memory.tombstone import TombstoneFilter

    tombstone = TombstoneFilter()
    tombstone.add("tenant_t", "app_t", "mem_a")
    wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "stub_a"}),
        adapters={"stub_a": StubMemoryAdapter([_entry("mem_a")]), "null": NullMemoryAdapter()},
        tombstone_filter=tombstone,
    )

    result = wrapper.get(
        MemoryGetRequest(tenant_id="tenant_t", application_id="app_t", entity_id="mem_a")
    )
    assert result is None


# --- failure paths for get / upsert / delete ---

def test_get_failure_raises_and_records_metric() -> None:
    from totalrecall.memory.models import MemoryGetRequest

    class _BrokenAdapter:
        adapter_version = "broken"
        def get(self, request): raise RuntimeError("get broke")
        def search(self, request): raise RuntimeError("search broke")
        def upsert(self, request): raise RuntimeError("upsert broke")
        def delete(self, request): raise RuntimeError("delete broke")
        def health(self): raise RuntimeError("health broke")
        def capabilities(self): raise RuntimeError("caps broke")

    wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "broken"}),
        adapters={"broken": _BrokenAdapter(), "null": NullMemoryAdapter()},
    )

    import pytest
    with pytest.raises(RuntimeError, match="get broke"):
        wrapper.get(
            MemoryGetRequest(tenant_id="t", application_id="a", entity_id="m1")
        )
    stats = wrapper.operation_stats()
    assert stats["get_failure_total"] == 1


def test_upsert_failure_raises_and_records_metric() -> None:
    class _BrokenAdapter:
        adapter_version = "broken"
        def upsert(self, request): raise RuntimeError("upsert broke")

    wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "broken"}),
        adapters={"broken": _BrokenAdapter(), "null": NullMemoryAdapter()},
    )

    import pytest
    with pytest.raises(RuntimeError, match="upsert broke"):
        wrapper.upsert(MemoryUpsertRequest(memory=_entry("m1")))
    stats = wrapper.operation_stats()
    assert stats["upsert_failure_total"] == 1


def test_delete_failure_raises_and_records_metric() -> None:
    from totalrecall.memory.models import MemoryDeleteRequest

    class _BrokenAdapter:
        adapter_version = "broken"
        def delete(self, request): raise RuntimeError("delete broke")

    wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "broken"}),
        adapters={"broken": _BrokenAdapter(), "null": NullMemoryAdapter()},
    )

    import pytest
    with pytest.raises(RuntimeError, match="delete broke"):
        wrapper.delete(
            MemoryDeleteRequest(tenant_id="t", application_id="a", entity_id="m1", deleted_by="u")
        )
    stats = wrapper.operation_stats()
    assert stats["delete_failure_total"] == 1


# --- active_adapter_name public method ---

def test_active_adapter_name_returns_configured_adapter() -> None:
    wrapper = _build_wrapper(primary="stub_a")
    assert wrapper.active_adapter_name() == "stub_a"
