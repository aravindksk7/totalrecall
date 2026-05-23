"""Security tests: tenant isolation and RBAC enforcement across the API.

These tests verify security properties that must hold regardless of feature flags
or database state. They are intentionally narrow — each test proves one invariant.
"""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from totalrecall.api.dependencies import (
    get_audit_repo,
    get_catalogue_repo,
    get_learning_repo,
    get_tombstone_filter,
    get_tombstone_repo,
)
from totalrecall.memory.tombstone import TombstoneFilter
from totalrecall.auth.models import AuthTokenConfig
from totalrecall.config.settings import Settings
from totalrecall.main import create_app


def _settings() -> Settings:
    return Settings(
        environment="test",
        enable_database=False,
        auth_tokens={
            "token-tenant-a": AuthTokenConfig(
                tenant_id="tenant_a",
                actor_id="actor_a",
                roles=["admin"],
            ),
            "token-tenant-b": AuthTokenConfig(
                tenant_id="tenant_b",
                actor_id="actor_b",
                roles=["admin"],
            ),
            "reader-tenant-a": AuthTokenConfig(
                tenant_id="tenant_a",
                actor_id="reader_a",
                roles=["reader"],
            ),
        },
        feature_flags={"memory.adapter": "stub"},
    )


def _generation_body(tenant_id: str) -> dict:
    return {
        "tenant_id": tenant_id,
        "application_id": "app_test",
        "prompt": "Generate a login page object",
        "target": {
            "language": "typescript",
            "framework": "playwright",
            "pattern": "pom",
            "locator_strategy": "page_file",
        },
        "scope": {"domain": "auth", "route": "login"},
    }


def _mock_learning_repo() -> MagicMock:
    repo = MagicMock()
    repo.save_report = AsyncMock(return_value=None)
    repo.get_run = AsyncMock(return_value=None)
    repo.list_runs = AsyncMock(return_value=[])
    repo.get_previous_hashes = AsyncMock(return_value={})
    repo.approve_discovery = AsyncMock(return_value=True)
    repo.reject_discovery = AsyncMock(return_value=True)
    repo.get_discovery = AsyncMock(return_value=None)
    return repo


def _mock_audit_repo() -> MagicMock:
    repo = MagicMock()
    repo.record = AsyncMock(return_value="evt_001")
    return repo


def _mock_catalogue_repo() -> MagicMock:
    repo = MagicMock()
    repo.upsert = AsyncMock(return_value=None)
    return repo


def _mock_tombstone_repo() -> MagicMock:
    repo = MagicMock()
    repo.add = AsyncMock(return_value=None)
    return repo


def _client_with_mocked_repos() -> TestClient:
    app = create_app(_settings())
    app.dependency_overrides[get_learning_repo] = lambda: _mock_learning_repo()
    app.dependency_overrides[get_audit_repo] = lambda: _mock_audit_repo()
    app.dependency_overrides[get_catalogue_repo] = lambda: _mock_catalogue_repo()
    app.dependency_overrides[get_tombstone_repo] = lambda: _mock_tombstone_repo()
    app.dependency_overrides[get_tombstone_filter] = lambda: TombstoneFilter()
    return TestClient(app, raise_server_exceptions=True)


# --- Tenant isolation ---


def test_generation_rejects_cross_tenant_body() -> None:
    """Body tenant_id must match the auth token's tenant."""
    app = create_app(_settings())
    with TestClient(app) as client:
        response = client.post(
            "/v1/generations",
            json=_generation_body("tenant_b"),  # auth is for tenant_a
            headers={"Authorization": "Bearer token-tenant-a"},
        )
    assert response.status_code == 403


def test_generation_accepts_matching_tenant_body() -> None:
    """Body tenant_id matching the auth token is allowed."""
    app = create_app(_settings())
    with TestClient(app) as client:
        response = client.post(
            "/v1/generations",
            json=_generation_body("tenant_a"),
            headers={"Authorization": "Bearer token-tenant-a"},
        )
    assert response.status_code == 200


# --- Unauthenticated access ---


def test_unauthenticated_generation_is_rejected() -> None:
    app = create_app(_settings())
    with TestClient(app) as client:
        response = client.post("/v1/generations", json=_generation_body("tenant_a"))
    assert response.status_code == 401


def test_invalid_token_is_rejected() -> None:
    app = create_app(_settings())
    with TestClient(app) as client:
        response = client.post(
            "/v1/generations",
            json=_generation_body("tenant_a"),
            headers={"Authorization": "Bearer not-a-real-token"},
        )
    assert response.status_code == 401


def test_malformed_authorization_header_is_rejected() -> None:
    app = create_app(_settings())
    with TestClient(app) as client:
        response = client.post(
            "/v1/generations",
            json=_generation_body("tenant_a"),
            headers={"Authorization": "token-tenant-a"},  # missing "Bearer " prefix
        )
    assert response.status_code == 401


# --- RBAC: reader cannot perform write operations ---


def test_reader_cannot_delete_memory() -> None:
    """memory:delete permission is required; reader role lacks it."""
    with _client_with_mocked_repos() as client:
        response = client.request(
            "DELETE",
            "/v1/memories/mem_001",
            json={"application_id": "app_test"},
            headers={"Authorization": "Bearer reader-tenant-a"},
        )
    assert response.status_code == 403


def test_reader_cannot_trigger_learning_run() -> None:
    """learning:promote permission is required; reader role lacks it."""
    with _client_with_mocked_repos() as client:
        response = client.post(
            "/v1/learning/runs",
            json={
                "application_id": "app_test",
                "scope": {"repository": "local", "branch": "main", "path": "/tmp"},
            },
            headers={"Authorization": "Bearer reader-tenant-a"},
        )
    assert response.status_code == 403


def test_reader_cannot_approve_discovery() -> None:
    """learning:promote permission is required to approve discoveries."""
    with _client_with_mocked_repos() as client:
        response = client.post(
            "/v1/learning/runs/run_001/approve/disc_001",
            json={},
            headers={"Authorization": "Bearer reader-tenant-a"},
        )
    assert response.status_code == 403


def test_reader_cannot_reject_discovery() -> None:
    """learning:promote permission is required to reject discoveries."""
    with _client_with_mocked_repos() as client:
        response = client.post(
            "/v1/learning/runs/run_001/reject/disc_001",
            json={},
            headers={"Authorization": "Bearer reader-tenant-a"},
        )
    assert response.status_code == 403


# --- Health endpoint is public ---


def test_health_endpoint_requires_no_auth() -> None:
    app = create_app(_settings())
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
