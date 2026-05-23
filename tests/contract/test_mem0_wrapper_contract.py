from typing import Any

import httpx
from mem0 import MemoryClient

from totalrecall.config.feature_flags import ConfigFeatureFlagProvider
from totalrecall.memory.adapters.mem0_v1.adapter import Mem0V1Adapter
from totalrecall.memory.adapters.null import NullMemoryAdapter
from totalrecall.memory.models import (
    MemoryDeleteRequest,
    MemoryEntry,
    MemoryGetRequest,
    MemorySearchRequest,
    MemoryStatus,
    MemoryUpsertRequest,
)
from totalrecall.memory.tombstone import TombstoneFilter
from totalrecall.memory.wrapper import MemoryWrapper


class _CredentialProvider:
    def get(self, key: str) -> str:
        _ = key
        return "mem0-test-key"


class _Mem0ContractTransport(httpx.BaseTransport):
    def __init__(self) -> None:
        self.entries: dict[str, dict[str, Any]] = {
            "mem_remote_001": {
                "id": "mem_remote_001",
                "memory": "Login uses role button named Sign in.",
                "metadata": {"domain": "authentication"},
            }
        }
        self.deleted: list[str] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/ping/":
            return httpx.Response(
                200,
                json={"org_id": "org", "project_id": "project", "user_email": "test@example.test"},
                request=request,
            )

        if request.url.path == "/v3/memories/search/":
            return httpx.Response(
                200,
                json={"results": list(self.entries.values())},
                request=request,
            )

        if request.url.path == "/v3/memories/add/":
            entry = {
                "id": "mem_remote_002",
                "memory": "Checkout: Checkout starts at /checkout.",
                "metadata": {},
            }
            self.entries["mem_remote_002"] = entry
            return httpx.Response(200, json={"results": [entry]}, request=request)

        if request.url.path.startswith("/v1/memories/") and request.method == "GET":
            entity_id = request.url.path.removeprefix("/v1/memories/").removesuffix("/")
            entry = self.entries.get(entity_id)
            status_code = 200 if entry is not None else 404
            return httpx.Response(
                status_code,
                json=entry or {"detail": "not found"},
                request=request,
            )

        if request.url.path.startswith("/v1/memories/") and request.method == "DELETE":
            entity_id = request.url.path.removeprefix("/v1/memories/").removesuffix("/")
            self.deleted.append(entity_id)
            self.entries.pop(entity_id, None)
            return httpx.Response(200, json={"deleted": True}, request=request)

        return httpx.Response(404, json={"detail": request.url.path}, request=request)


def _memory_client(transport: _Mem0ContractTransport) -> MemoryClient:
    return MemoryClient(
        api_key="mem0-test-key",
        host="https://mem0.example.test",
        client=httpx.Client(transport=transport),
    )


def _build_mem0_wrapper(transport: _Mem0ContractTransport) -> MemoryWrapper:
    return MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "mem0_v1"}),
        adapters={
            "mem0_v1": Mem0V1Adapter(
                _CredentialProvider(),
                client=_memory_client(transport),
            ),
            "null": NullMemoryAdapter(),
        },
    )


def test_mem0_adapter_satisfies_wrapper_search_get_upsert_delete_contract() -> None:
    transport = _Mem0ContractTransport()
    wrapper = _build_mem0_wrapper(transport)

    search_result = wrapper.search(
        MemorySearchRequest(
            tenant_id="tenant_test",
            application_id="app_test",
            query="login",
        )
    )
    assert search_result.adapter_version == "mem0_v1"
    assert [entry.entity_id for entry in search_result.items] == ["mem_remote_001"]

    found = wrapper.get(
        MemoryGetRequest(
            tenant_id="tenant_test",
            application_id="app_test",
            entity_id="mem_remote_001",
        )
    )
    assert found is not None
    assert found.tags == {"domain": "authentication"}

    upserted = wrapper.upsert(
        MemoryUpsertRequest(
            memory=MemoryEntry(
                entity_id="mem_local",
                tenant_id="tenant_test",
                application_id="app_test",
                summary="Checkout",
                knowledge="Checkout starts at /checkout.",
            )
        )
    )
    assert upserted.entity_id == "mem_remote_002"

    delete_result = wrapper.delete(
        MemoryDeleteRequest(
            tenant_id="tenant_test",
            application_id="app_test",
            entity_id="mem_remote_001",
            deleted_by="actor_admin",
        )
    )
    assert delete_result.deleted is True
    assert transport.deleted == ["mem_remote_001"]


def test_mem0_wrapper_applies_tombstones_to_search_results() -> None:
    transport = _Mem0ContractTransport()
    tombstones = TombstoneFilter()
    tombstones.add("tenant_test", "app_test", "mem_remote_001")
    wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "mem0_v1"}),
        adapters={
            "mem0_v1": Mem0V1Adapter(
                _CredentialProvider(),
                client=_memory_client(transport),
            ),
            "null": NullMemoryAdapter(),
        },
        tombstone_filter=tombstones,
    )

    result = wrapper.search(
        MemorySearchRequest(tenant_id="tenant_test", application_id="app_test")
    )

    assert result.items == []


def test_mem0_wrapper_filters_deleted_mem0_entries() -> None:
    transport = _Mem0ContractTransport()
    transport.entries["mem_deleted"] = {
        "id": "mem_deleted",
        "memory": "Deleted memory",
        "metadata": {},
        "status": MemoryStatus.DELETED,
    }
    wrapper = _build_mem0_wrapper(transport)

    result = wrapper.search(
        MemorySearchRequest(tenant_id="tenant_test", application_id="app_test")
    )

    assert all(item.entity_id != "mem_deleted" for item in result.items)
