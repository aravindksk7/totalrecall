"""Integration tests for the standalone memory wrapper service app."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from totalrecall.auth.models import AuthTokenConfig
from totalrecall.config.settings import Settings
from totalrecall.memory.service_app import create_memory_app


def _settings() -> Settings:
    return Settings(
        environment="test",
        enable_database=False,
        auth_tokens={
            "admin-token": AuthTokenConfig(
                tenant_id="tenant_test",
                actor_id="actor_admin",
                roles=["admin"],
            ),
            "maintainer-token": AuthTokenConfig(
                tenant_id="tenant_test",
                actor_id="actor_maintainer",
                roles=["maintainer"],
            ),
            "reader-token": AuthTokenConfig(
                tenant_id="tenant_test",
                actor_id="actor_reader",
                roles=["reader"],
            ),
        },
        feature_flags={"memory.adapter": "stub"},
    )


@pytest.fixture
def client(tmp_path) -> Generator[TestClient]:
    settings = _settings()
    settings = settings.model_copy(update={"local_secrets_dir": tmp_path / "secrets"})
    with TestClient(create_memory_app(settings)) as test_client:
        yield test_client


def _memory_payload(entity_id: str = "mem_login") -> dict:
    return {
        "memory": {
            "entity_id": entity_id,
            "tenant_id": "tenant_test",
            "application_id": "app_test",
            "summary": "Login behaviour",
            "knowledge": "Login uses role button named Sign in.",
            "tags": {"domain": "authentication"},
        }
    }


def test_memory_service_health_is_public(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["adapter_version"] == "stub"


def test_memory_service_search_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/v1/memory/search",
        json={"tenant_id": "tenant_test", "application_id": "app_test"},
    )

    assert response.status_code == 401


def test_memory_service_upsert_search_get_and_delete(client: TestClient) -> None:
    upsert = client.post(
        "/v1/memory/upsert",
        json=_memory_payload(),
        headers={"Authorization": "Bearer maintainer-token"},
    )
    assert upsert.status_code == 200

    search = client.post(
        "/v1/memory/search",
        json={
            "tenant_id": "tenant_test",
            "application_id": "app_test",
            "filters": {"domain": "authentication"},
        },
        headers={"Authorization": "Bearer reader-token"},
    )
    assert search.status_code == 200
    assert [item["entity_id"] for item in search.json()["items"]] == ["mem_login"]

    get = client.post(
        "/v1/memory/get",
        json={
            "tenant_id": "tenant_test",
            "application_id": "app_test",
            "entity_id": "mem_login",
        },
        headers={"Authorization": "Bearer reader-token"},
    )
    assert get.status_code == 200
    assert get.json()["summary"] == "Login behaviour"

    delete = client.post(
        "/v1/memory/delete",
        json={
            "tenant_id": "tenant_test",
            "application_id": "app_test",
            "entity_id": "mem_login",
            "deleted_by": "actor_admin",
        },
        headers={"Authorization": "Bearer admin-token"},
    )
    assert delete.status_code == 200
    assert delete.json()["deleted"] is True


def test_memory_service_rejects_upsert_without_write_permission(client: TestClient) -> None:
    response = client.post(
        "/v1/memory/upsert",
        json=_memory_payload(),
        headers={"Authorization": "Bearer reader-token"},
    )

    assert response.status_code == 403


def test_memory_service_rejects_cross_tenant_request(client: TestClient) -> None:
    response = client.post(
        "/v1/memory/search",
        json={"tenant_id": "other_tenant", "application_id": "app_test"},
        headers={"Authorization": "Bearer reader-token"},
    )

    assert response.status_code == 403


def test_memory_service_requires_deleted_by_actor_match(client: TestClient) -> None:
    response = client.post(
        "/v1/memory/delete",
        json={
            "tenant_id": "tenant_test",
            "application_id": "app_test",
            "entity_id": "mem_login",
            "deleted_by": "someone_else",
        },
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 403
