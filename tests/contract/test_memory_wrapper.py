from totalrecall.config.feature_flags import ConfigFeatureFlagProvider
from totalrecall.memory.adapters.null import NullMemoryAdapter
from totalrecall.memory.adapters.stub import StubMemoryAdapter
from totalrecall.memory.models import (
    MemoryDeleteRequest,
    MemoryEntry,
    MemoryGetRequest,
    MemorySearchRequest,
    MemoryUpsertRequest,
)
from totalrecall.memory.wrapper import MemoryWrapper


def build_wrapper(adapter_name: str = "stub") -> MemoryWrapper:
    return MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": adapter_name}),
        adapters={
            "stub": StubMemoryAdapter(
                [
                    MemoryEntry(
                        entity_id="mem_login",
                        tenant_id="tenant_test",
                        application_id="app_test",
                        summary="Login button",
                        knowledge="Login button uses role button named Login.",
                        tags={"domain": "authentication"},
                    )
                ]
            ),
            "null": NullMemoryAdapter(),
        },
    )


def test_stub_adapter_searches_by_tenant_application_and_filter() -> None:
    wrapper = build_wrapper()

    result = wrapper.search(
        MemorySearchRequest(
            tenant_id="tenant_test",
            application_id="app_test",
            filters={"domain": "authentication"},
        )
    )

    assert result.adapter_version == "stub"
    assert [entry.entity_id for entry in result.items] == ["mem_login"]
    stats = wrapper.operation_stats()
    assert stats["search_total"] == 1
    assert stats["search_success_total"] == 1
    assert stats["search_failure_total"] == 0


def test_stub_adapter_upserts_gets_and_deletes_memory() -> None:
    wrapper = build_wrapper()
    memory = MemoryEntry(
        entity_id="mem_checkout",
        tenant_id="tenant_test",
        application_id="app_test",
        summary="Checkout",
        knowledge="Checkout starts at /checkout.",
    )

    wrapper.upsert(MemoryUpsertRequest(memory=memory))
    found = wrapper.get(
        MemoryGetRequest(
            tenant_id="tenant_test",
            application_id="app_test",
            entity_id="mem_checkout",
        )
    )

    assert found == memory

    delete_result = wrapper.delete(
        MemoryDeleteRequest(
            tenant_id="tenant_test",
            application_id="app_test",
            entity_id="mem_checkout",
            deleted_by="actor_admin",
        )
    )

    assert delete_result.deleted is True
    assert (
        wrapper.get(
            MemoryGetRequest(
                tenant_id="tenant_test",
                application_id="app_test",
                entity_id="mem_checkout",
            )
        )
        is None
    )
    stats = wrapper.operation_stats()
    assert stats["upsert_total"] == 1
    assert stats["get_total"] == 2
    assert stats["delete_total"] == 1


def test_null_adapter_provides_degraded_empty_memory_path() -> None:
    wrapper = build_wrapper("null")

    result = wrapper.search(
        MemorySearchRequest(
            tenant_id="tenant_test",
            application_id="app_test",
        )
    )

    assert result.items == []
    assert wrapper.health().degraded is True


def test_adapter_routes_by_feature_flag() -> None:
    """Changing the feature flag value selects the corresponding adapter."""
    stub_wrapper = build_wrapper("stub")
    null_wrapper = build_wrapper("null")

    stub_result = stub_wrapper.search(
        MemorySearchRequest(tenant_id="tenant_test", application_id="app_test")
    )
    null_result = null_wrapper.search(
        MemorySearchRequest(tenant_id="tenant_test", application_id="app_test")
    )

    assert stub_result.adapter_version == "stub"
    assert null_result.adapter_version == "null"
    assert len(stub_result.items) > 0
    assert len(null_result.items) == 0


def test_tombstone_filter_excludes_deleted_memories() -> None:
    """Memories whose entity_ids appear in the tombstone filter are excluded from search."""
    from totalrecall.memory.tombstone import TombstoneFilter

    tombstone_filter = TombstoneFilter()
    tombstone_filter.add("tenant_test", "app_test", "mem_login")

    wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "stub"}),
        adapters={
            "stub": StubMemoryAdapter(
                [
                    MemoryEntry(
                        entity_id="mem_login",
                        tenant_id="tenant_test",
                        application_id="app_test",
                        summary="Login button",
                        knowledge="Login uses role button.",
                        tags={"domain": "authentication"},
                    )
                ]
            ),
            "null": NullMemoryAdapter(),
        },
        tombstone_filter=tombstone_filter,
    )

    result = wrapper.search(
        MemorySearchRequest(tenant_id="tenant_test", application_id="app_test")
    )

    assert all(item.entity_id != "mem_login" for item in result.items)


def test_stub_health_is_not_degraded() -> None:
    wrapper = build_wrapper("stub")
    assert wrapper.health().degraded is False


def test_null_health_is_degraded() -> None:
    wrapper = build_wrapper("null")
    assert wrapper.health().degraded is True


def test_wrapper_capabilities_reflect_adapter() -> None:
    stub_wrapper = build_wrapper("stub")
    null_wrapper = build_wrapper("null")

    assert stub_wrapper.capabilities().supports_search is True
    assert null_wrapper.capabilities().supports_upsert is False
    assert null_wrapper.capabilities().supports_delete is False
