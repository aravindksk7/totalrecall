"""Integration tests for runtime monitoring endpoints."""

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


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer admin-token"}


def _generation_body() -> dict:
    return {
        "tenant_id": "tenant_test",
        "application_id": "app_test",
        "prompt": "Generate a page object for login",
        "target": {
            "language": "typescript",
            "framework": "playwright",
            "pattern": "pom",
            "locator_strategy": "page_file",
        },
        "scope": {"domain": "auth"},
        "options": {"validate": False},
    }


def test_monitoring_summary_returns_memory_provider_and_token_state(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/v1/monitoring/summary", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["memory"]["configured_adapter"] == "stub"
    assert body["memory"]["operations"]["search_total"] == 0
    assert body["memory"]["mem0"]["credential_configured"] is False
    assert body["memory"]["mem0"]["host_configured"] is False
    assert body["token_efficiency"]["generations_total"] == 0
    provider_ids = {provider["provider_id"] for provider in body["providers"]}
    assert {"stub", "openai", "local", "claude", "gemini"} <= provider_ids


def test_monitoring_reflects_generation_context_and_memory_search(tmp_path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        client.post("/v1/generations", json=_generation_body(), headers=_headers())
        response = client.get("/v1/monitoring/summary", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["memory"]["operations"]["search_total"] >= 1
    assert body["token_efficiency"]["generations_total"] == 1
    assert body["token_efficiency"]["last_context_plan_id"]
    assert body["token_efficiency"]["last_estimated_input_tokens"] > 0


def test_monitoring_requires_authentication(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/v1/monitoring/summary")

    assert response.status_code == 401
