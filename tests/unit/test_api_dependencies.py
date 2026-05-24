"""Unit tests for API dependency helpers — especially 503 paths when database is off."""

import pytest
from fastapi.testclient import TestClient

from totalrecall.auth.models import AuthTokenConfig
from totalrecall.config.settings import Settings
from totalrecall.main import create_app


def _settings(tmp_path) -> Settings:
    return Settings(
        environment="test",
        enable_database=False,
        local_secrets_dir=tmp_path / "secrets",
        auth_tokens={
            "admin-token": AuthTokenConfig(
                tenant_id="tenant_test",
                actor_id="actor_admin",
                roles=["admin"],
            ),
        },
        feature_flags={"memory.adapter": "stub"},
    )


_ADMIN = {"Authorization": "Bearer admin-token"}


def test_get_credential_provider_is_accessible_via_monitoring(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/v1/monitoring/memory", headers=_ADMIN)

    assert response.status_code == 200


def test_learning_repo_unavailable_returns_503(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/v1/learning/runs", headers=_ADMIN)

    assert response.status_code == 503
    assert "Database" in response.json()["detail"]


def test_learning_trigger_unavailable_returns_503(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.post(
            "/v1/learning/runs",
            json={
                "application_id": "app_test",
                "scope": {"path": "/tmp/test"},
                "trigger_type": "manual",
            },
            headers=_ADMIN,
        )

    assert response.status_code == 503


def test_catalogue_repo_unavailable_returns_503(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/v1/catalogue", headers=_ADMIN)

    assert response.status_code == 503


def test_tombstone_repo_unavailable_on_delete_returns_503(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.request(
            "DELETE",
            "/v1/memories/some-entity-id",
            content='{"application_id":"app_test"}',
            headers={**_ADMIN, "Content-Type": "application/json"},
        )

    assert response.status_code == 503


def test_audit_repo_unavailable_reflected_in_generation(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.post(
            "/v1/generations",
            json={
                "tenant_id": "tenant_test",
                "application_id": "app_test",
                "prompt": "Generate login test",
                "target": {
                    "language": "typescript",
                    "framework": "playwright",
                    "pattern": "pom",
                    "locator_strategy": "page_file",
                },
                "scope": {"domain": "auth"},
                "options": {"validate": False},
            },
            headers=_ADMIN,
        )

    # Generation succeeds even without DB (audit_repo is optional in orchestrator)
    assert response.status_code == 200
