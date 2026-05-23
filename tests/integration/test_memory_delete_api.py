"""Integration tests for DELETE /v1/memories/{entity_id}."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from totalrecall.api.dependencies import (
    get_audit_repo,
    get_tombstone_filter,
    get_tombstone_repo,
)
from totalrecall.auth.models import AuthTokenConfig
from totalrecall.config.settings import Settings
from totalrecall.main import create_app
from totalrecall.memory.tombstone import TombstoneFilter


def _make_settings() -> Settings:
    return Settings(
        environment="test",
        enable_database=False,
        auth_tokens={
            "test-admin": AuthTokenConfig(
                tenant_id="tenant_test",
                actor_id="actor_admin",
                roles=["admin"],
            ),
            "test-reader": AuthTokenConfig(
                tenant_id="tenant_test",
                actor_id="actor_reader",
                roles=["reader"],
            ),
        },
        feature_flags={"memory.adapter": "stub"},
    )


def _make_tombstone_repo() -> MagicMock:
    repo = MagicMock()
    repo.add = AsyncMock(return_value=None)
    repo.exists = AsyncMock(return_value=False)
    repo.load_all = AsyncMock(return_value=[])
    return repo


def _make_audit_repo() -> MagicMock:
    repo = MagicMock()
    repo.record = AsyncMock(return_value="event_001")
    return repo


def _delete_body(application_id: str = "app_test", reason: str | None = "test cleanup") -> dict:
    return {"application_id": application_id, "reason": reason}


def _delete(client: TestClient, url: str, body: dict, token: str | None = None) -> object:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return client.request("DELETE", url, json=body, headers=headers)


@pytest.fixture
def tombstone_filter() -> TombstoneFilter:
    return TombstoneFilter()


@pytest.fixture
def client_with_db(tombstone_filter: TombstoneFilter) -> Generator[TestClient]:
    settings = _make_settings()
    app = create_app(settings)
    tombstone_repo = _make_tombstone_repo()
    audit_repo = _make_audit_repo()

    app.dependency_overrides[get_tombstone_filter] = lambda: tombstone_filter
    app.dependency_overrides[get_tombstone_repo] = lambda: tombstone_repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo

    with TestClient(app) as test_client:
        yield test_client


def test_delete_memory_returns_503_when_db_unavailable() -> None:
    settings = _make_settings()
    app = create_app(settings)
    with TestClient(app) as client:
        response = _delete(client, "/v1/memories/mem_001", _delete_body(), token="test-admin")

    assert response.status_code == 503


def test_delete_memory_rejects_missing_auth(client_with_db) -> None:
    response = _delete(client_with_db, "/v1/memories/mem_001", _delete_body())

    assert response.status_code == 401


def test_delete_memory_rejects_reader_without_permission(client_with_db) -> None:
    response = _delete(
        client_with_db, "/v1/memories/mem_001", _delete_body(), token="test-reader"
    )

    assert response.status_code == 403


def test_delete_memory_succeeds_for_admin(client_with_db) -> None:
    response = _delete(
        client_with_db, "/v1/memories/mem_001", _delete_body(), token="test-admin"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["entity_id"] == "mem_001"
    assert body["deleted"] is True
    assert body["tombstoned"] is True


def test_delete_memory_adds_to_tombstone_filter(
    client_with_db, tombstone_filter: TombstoneFilter
) -> None:
    _delete(client_with_db, "/v1/memories/mem_filter_test", _delete_body(), token="test-admin")

    assert tombstone_filter.is_tombstoned("tenant_test", "app_test", "mem_filter_test") is True


def test_delete_memory_writes_to_tombstone_repo(tombstone_filter: TombstoneFilter) -> None:
    settings = _make_settings()
    app = create_app(settings)
    tombstone_repo = _make_tombstone_repo()
    audit_repo = _make_audit_repo()

    app.dependency_overrides[get_tombstone_filter] = lambda: tombstone_filter
    app.dependency_overrides[get_tombstone_repo] = lambda: tombstone_repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo

    with TestClient(app) as client:
        _delete(
            client,
            "/v1/memories/mem_repo_test",
            _delete_body(reason="integration test"),
            token="test-admin",
        )

    tombstone_repo.add.assert_awaited_once()
    call_kwargs = tombstone_repo.add.call_args.kwargs
    assert call_kwargs["entity_id"] == "mem_repo_test"
    assert call_kwargs["tenant_id"] == "tenant_test"
    assert call_kwargs["reason"] == "integration test"


def test_delete_memory_records_audit_event(tombstone_filter: TombstoneFilter) -> None:
    settings = _make_settings()
    app = create_app(settings)
    tombstone_repo = _make_tombstone_repo()
    audit_repo = _make_audit_repo()

    app.dependency_overrides[get_tombstone_filter] = lambda: tombstone_filter
    app.dependency_overrides[get_tombstone_repo] = lambda: tombstone_repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo

    with TestClient(app) as client:
        _delete(client, "/v1/memories/mem_audit_test", _delete_body(), token="test-admin")

    audit_repo.record.assert_awaited_once()
    call_kwargs = audit_repo.record.call_args.kwargs
    assert call_kwargs["event_type"] == "memory.deleted"
    assert call_kwargs["subject_id"] == "mem_audit_test"
    assert call_kwargs["tenant_id"] == "tenant_test"
    assert call_kwargs["actor_id"] == "actor_admin"


def test_delete_memory_without_reason_succeeds(client_with_db) -> None:
    response = _delete(
        client_with_db, "/v1/memories/mem_no_reason", _delete_body(reason=None), token="test-admin"
    )

    assert response.status_code == 200


def test_delete_memory_rejects_invalid_body(client_with_db) -> None:
    response = _delete(
        client_with_db, "/v1/memories/mem_001", {"bad_field": "value"}, token="test-admin"
    )

    assert response.status_code == 422
