"""Unit tests for Mem0V1Adapter using the installed mem0ai SDK."""

import json
from typing import Any

import httpx
import pytest
from mem0 import MemoryClient

from totalrecall.memory.adapters.mem0_v1.adapter import (
    Mem0V1Adapter,
    _extract_mem0_results,
    _mem0_filters,
    _mem0_user_id,
)
from totalrecall.memory.models import (
    MemoryDeleteRequest,
    MemoryEntry,
    MemoryGetRequest,
    MemoryHealthStatus,
    MemorySearchRequest,
    MemoryStatus,
    MemoryUpsertRequest,
)


class _CredentialProvider:
    def __init__(self, value: str = "mem0-test-key") -> None:
        self.value = value
        self.calls: list[str] = []

    def get(self, key: str) -> str:
        self.calls.append(key)
        return self.value


class _Mem0Transport(httpx.BaseTransport):
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.search_results: list[dict[str, Any]] = [
            {
                "id": "mem_remote_001",
                "memory": "Login uses role button.",
                "metadata": {"domain": "auth"},
            }
        ]
        self.get_result: dict[str, Any] | None = self.search_results[0]
        self.add_result: dict[str, Any] = {
            "id": "mem_remote_002",
            "memory": "Checkout: Checkout starts at /checkout.",
            "metadata": {"domain": "checkout"},
        }
        self.fail_paths: set[str] = set()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path in self.fail_paths:
            return httpx.Response(
                500,
                json={"detail": "forced failure"},
                request=request,
            )

        if request.url.path == "/v1/ping/":
            return httpx.Response(
                200,
                json={
                    "org_id": "org_test",
                    "project_id": "project_test",
                    "user_email": "tester@example.test",
                },
                request=request,
            )

        if request.url.path == "/v3/memories/search/" and request.method == "POST":
            return httpx.Response(200, json={"results": self.search_results}, request=request)

        if request.url.path == "/v3/memories/add/" and request.method == "POST":
            return httpx.Response(200, json={"results": [self.add_result]}, request=request)

        if request.url.path.startswith("/v1/memories/") and request.method == "GET":
            if self.get_result is None:
                return httpx.Response(404, json={"detail": "not found"}, request=request)
            return httpx.Response(200, json=self.get_result, request=request)

        if request.url.path.startswith("/v1/memories/") and request.method == "DELETE":
            return httpx.Response(200, json={"deleted": True}, request=request)

        return httpx.Response(404, json={"detail": request.url.path}, request=request)


def _client(transport: _Mem0Transport) -> MemoryClient:
    return MemoryClient(
        api_key="mem0-test-key",
        host="https://mem0.example.test",
        client=httpx.Client(transport=transport),
    )


def _adapter(transport: _Mem0Transport | None = None) -> tuple[Mem0V1Adapter, _Mem0Transport]:
    resolved_transport = transport or _Mem0Transport()
    adapter = Mem0V1Adapter(_CredentialProvider(), client=_client(resolved_transport))
    return adapter, resolved_transport


def _json_body(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content.decode("utf-8"))


def test_search_returns_active_entries() -> None:
    adapter, _ = _adapter()

    result = adapter.search(
        MemorySearchRequest(
            tenant_id="t1",
            application_id="app1",
            query="login",
        )
    )

    assert len(result.items) == 1
    assert result.items[0].entity_id == "mem_remote_001"
    assert result.adapter_version == "mem0_v1"


def test_search_sends_v3_filters_and_top_k() -> None:
    adapter, transport = _adapter()

    adapter.search(
        MemorySearchRequest(
            tenant_id="t1",
            application_id="app1",
            query="login",
            filters={"domain": "auth"},
            limit=3,
        )
    )

    search_request = [r for r in transport.requests if r.url.path == "/v3/memories/search/"][0]
    body = _json_body(search_request)
    assert body["query"] == "login"
    assert body["top_k"] == 3
    assert body["filters"] == {"AND": [{"user_id": "t1::app1"}, {"domain": "auth"}]}


def test_search_returns_empty_on_exception() -> None:
    transport = _Mem0Transport()
    transport.fail_paths.add("/v3/memories/search/")
    adapter, _ = _adapter(transport)

    result = adapter.search(
        MemorySearchRequest(tenant_id="t1", application_id="app1", query="login")
    )

    assert result.items == []


def test_search_filters_deleted_entries() -> None:
    transport = _Mem0Transport()
    transport.search_results.append(
        {"id": "mem_deleted", "memory": "deleted", "metadata": {}, "status": "deleted"}
    )
    adapter, _ = _adapter(transport)

    result = adapter.search(MemorySearchRequest(tenant_id="t1", application_id="app1"))

    assert [entry.entity_id for entry in result.items] == ["mem_remote_001"]


def test_get_returns_entry_when_found() -> None:
    adapter, _ = _adapter()

    entry = adapter.get(
        MemoryGetRequest(
            tenant_id="t1",
            application_id="app1",
            entity_id="mem_remote_001",
        )
    )

    assert entry is not None
    assert entry.entity_id == "mem_remote_001"
    assert entry.knowledge == "Login uses role button."


def test_get_returns_none_when_not_found() -> None:
    transport = _Mem0Transport()
    transport.get_result = None
    adapter, _ = _adapter(transport)

    entry = adapter.get(
        MemoryGetRequest(tenant_id="t1", application_id="app1", entity_id="mem_missing")
    )

    assert entry is None


def test_get_returns_none_on_exception() -> None:
    transport = _Mem0Transport()
    transport.fail_paths.add("/v1/memories/mem_err/")
    adapter, _ = _adapter(transport)

    entry = adapter.get(
        MemoryGetRequest(tenant_id="t1", application_id="app1", entity_id="mem_err")
    )

    assert entry is None


def test_upsert_returns_mem0_entry_on_success() -> None:
    memory = MemoryEntry(
        entity_id="mem_local",
        tenant_id="t1",
        application_id="app1",
        summary="Checkout",
        knowledge="Checkout starts at /checkout.",
        tags={"domain": "checkout"},
    )
    adapter, transport = _adapter()

    result = adapter.upsert(MemoryUpsertRequest(memory=memory))

    add_request = [r for r in transport.requests if r.url.path == "/v3/memories/add/"][0]
    body = _json_body(add_request)
    assert result.entity_id == "mem_remote_002"
    assert body["user_id"] == "t1::app1"
    assert body["metadata"] == {"domain": "checkout"}
    assert body["messages"][0]["role"] == "user"


def test_upsert_returns_original_entry_on_exception() -> None:
    transport = _Mem0Transport()
    transport.fail_paths.add("/v3/memories/add/")
    adapter, _ = _adapter(transport)
    memory = MemoryEntry(
        entity_id="mem_local",
        tenant_id="t1",
        application_id="app1",
        summary="Checkout",
        knowledge="Checkout at /checkout.",
    )

    result = adapter.upsert(MemoryUpsertRequest(memory=memory))

    assert result.entity_id == "mem_local"


def test_delete_returns_deleted_true_on_success() -> None:
    adapter, _ = _adapter()

    result = adapter.delete(
        MemoryDeleteRequest(
            tenant_id="t1",
            application_id="app1",
            entity_id="mem_remote_001",
            deleted_by="actor_admin",
        )
    )

    assert result.deleted is True
    assert result.entity_id == "mem_remote_001"


def test_delete_returns_deleted_false_on_exception() -> None:
    transport = _Mem0Transport()
    transport.fail_paths.add("/v1/memories/mem_missing/")
    adapter, _ = _adapter(transport)

    result = adapter.delete(
        MemoryDeleteRequest(
            tenant_id="t1",
            application_id="app1",
            entity_id="mem_missing",
            deleted_by="actor_admin",
        )
    )

    assert result.deleted is False


def test_health_returns_ok_when_client_initializes() -> None:
    adapter, _ = _adapter()

    health = adapter.health()

    assert health.status == MemoryHealthStatus.OK
    assert health.adapter_version == "mem0_v1"


def test_health_returns_unavailable_without_mem0(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> Any:
        if name == "mem0":
            raise ImportError("mem0 unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    adapter = Mem0V1Adapter(_CredentialProvider())

    health = adapter.health()

    assert health.status == MemoryHealthStatus.UNAVAILABLE
    assert health.degraded is True


def test_capabilities_reports_all_operations_supported() -> None:
    adapter, _ = _adapter()

    caps = adapter.capabilities()

    assert caps.supports_search is True
    assert caps.supports_get is True
    assert caps.supports_upsert is True
    assert caps.supports_delete is True
    assert caps.supports_shadow_read is False


def test_mem0_to_entry_handles_dict_format() -> None:
    raw = {"id": "m1", "memory": "some knowledge text", "metadata": {"domain": "auth"}}

    entry = Mem0V1Adapter._mem0_to_entry(raw, "t1", "app1")

    assert entry.entity_id == "m1"
    assert entry.knowledge == "some knowledge text"
    assert entry.tags == {"domain": "auth"}


def test_mem0_to_entry_handles_missing_id() -> None:
    raw: dict = {"memory": "text", "metadata": {}}

    entry = Mem0V1Adapter._mem0_to_entry(raw, "t1", "app1")

    assert entry.entity_id == "mem0_unknown"


def test_mem0_to_entry_truncates_long_summary() -> None:
    long_text = "x" * 200
    raw = {"id": "m1", "memory": long_text, "metadata": {}}

    entry = Mem0V1Adapter._mem0_to_entry(raw, "t1", "app1")

    assert len(entry.summary) == 120
    assert entry.knowledge == long_text


def test_mem0_to_entry_maps_status() -> None:
    raw = {"id": "m1", "memory": "deleted", "metadata": {}, "status": "deleted"}

    entry = Mem0V1Adapter._mem0_to_entry(raw, "t1", "app1")

    assert entry.status == MemoryStatus.DELETED


def test_user_id_scopes_to_tenant_and_application() -> None:
    assert _mem0_user_id("tenant_a", "app_b") == "tenant_a::app_b"


def test_mem0_filters_include_user_id_without_tag_filters() -> None:
    assert _mem0_filters("tenant::app", {}) == {"user_id": "tenant::app"}


def test_extract_mem0_results_accepts_result_envelope() -> None:
    assert _extract_mem0_results({"results": [{"id": "m1"}]}) == [{"id": "m1"}]
