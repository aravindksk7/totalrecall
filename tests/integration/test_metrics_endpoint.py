"""Integration tests for GET /v1/metrics."""

from fastapi.testclient import TestClient

from totalrecall.auth.models import AuthTokenConfig
from totalrecall.config.settings import Settings
from totalrecall.main import create_app


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
        },
        feature_flags={"memory.adapter": "stub"},
    )


def _generation_body() -> dict:
    return {
        "tenant_id": "tenant_test",
        "application_id": "app_test",
        "prompt": "Generate a page object",
        "target": {
            "language": "typescript",
            "framework": "playwright",
            "pattern": "pom",
            "locator_strategy": "page_file",
        },
        "scope": {"domain": "auth"},
        "options": {"validate": False},
    }


def test_metrics_endpoint_returns_200() -> None:
    with TestClient(create_app(_settings())) as client:
        response = client.get("/v1/metrics")
    assert response.status_code == 200


def test_metrics_initial_counters_are_zero() -> None:
    with TestClient(create_app(_settings())) as client:
        response = client.get("/v1/metrics")
    data = response.json()
    assert data["generations_total"] == 0
    assert data["generations_completed"] == 0


def test_metrics_increments_after_generation() -> None:
    app = create_app(_settings())
    with TestClient(app, raise_server_exceptions=True) as client:
        client.post(
            "/v1/generations",
            json=_generation_body(),
            headers={"Authorization": "Bearer admin-token"},
        )
        response = client.get("/v1/metrics")
    data = response.json()
    assert data["generations_total"] == 1
    assert data["generations_completed"] == 1
