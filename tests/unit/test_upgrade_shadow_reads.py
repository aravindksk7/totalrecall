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
