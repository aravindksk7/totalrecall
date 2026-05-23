"""Integration tests for per-tenant rate limiting on POST /v1/generations."""

from fastapi.testclient import TestClient

from totalrecall.auth.models import AuthTokenConfig
from totalrecall.config.settings import Settings
from totalrecall.main import create_app


def _settings_with_limit(max_requests: int = 2) -> Settings:
    return Settings(
        environment="test",
        enable_database=False,
        auth_tokens={
            "tenant-token": AuthTokenConfig(
                tenant_id="tenant_limited",
                actor_id="actor_test",
                roles=["generator"],
            ),
        },
        feature_flags={"memory.adapter": "stub"},
        rate_limits={"default": {"max_requests": max_requests, "window_seconds": 60}},
    )


def _generation_body() -> dict:
    return {
        "tenant_id": "tenant_limited",
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


def test_generation_succeeds_within_limit() -> None:
    app = create_app(_settings_with_limit(max_requests=5))
    with TestClient(app) as client:
        resp = client.post(
            "/v1/generations",
            json=_generation_body(),
            headers={"Authorization": "Bearer tenant-token"},
        )
    assert resp.status_code == 200


def test_generation_blocked_after_limit_exceeded() -> None:
    app = create_app(_settings_with_limit(max_requests=2))
    with TestClient(app) as client:
        client.post(
            "/v1/generations",
            json=_generation_body(),
            headers={"Authorization": "Bearer tenant-token"},
        )
        client.post(
            "/v1/generations",
            json=_generation_body(),
            headers={"Authorization": "Bearer tenant-token"},
        )
        resp = client.post(
            "/v1/generations",
            json=_generation_body(),
            headers={"Authorization": "Bearer tenant-token"},
        )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_no_rate_limit_config_always_allows() -> None:
    settings = Settings(
        environment="test",
        enable_database=False,
        auth_tokens={
            "tenant-token": AuthTokenConfig(
                tenant_id="tenant_limited",
                actor_id="actor_test",
                roles=["generator"],
            ),
        },
        feature_flags={"memory.adapter": "stub"},
        rate_limits={},
    )
    app = create_app(settings)
    with TestClient(app) as client:
        for _ in range(5):
            resp = client.post(
                "/v1/generations",
                json=_generation_body(),
                headers={"Authorization": "Bearer tenant-token"},
            )
            assert resp.status_code == 200
