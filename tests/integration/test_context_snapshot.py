"""Integration tests: context snapshot persistence wired into POST /v1/generations."""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from totalrecall.api.dependencies import get_optional_context_snapshot_repo
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
        "prompt": "Generate a login page object",
        "target": {
            "language": "typescript",
            "framework": "playwright",
            "pattern": "pom",
            "locator_strategy": "page_file",
        },
        "scope": {"domain": "auth", "route": "login"},
        "options": {"validate": False},
    }


def _make_snapshot_repo() -> MagicMock:
    repo = MagicMock()
    repo.save = AsyncMock(return_value=None)
    return repo


def test_context_snapshot_saved_on_generation() -> None:
    """After a successful generation, context snapshot repo.save is enqueued."""
    app = create_app(_settings())
    snapshot_repo = _make_snapshot_repo()
    app.dependency_overrides[get_optional_context_snapshot_repo] = lambda: snapshot_repo

    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.post(
            "/v1/generations",
            json=_generation_body(),
            headers={"Authorization": "Bearer admin-token"},
        )

    assert response.status_code == 200
    snapshot_repo.save.assert_called_once()
    call_kwargs = snapshot_repo.save.call_args.kwargs
    assert call_kwargs["tenant_id"] == "tenant_test"
    assert call_kwargs["application_id"] == "app_test"
    assert isinstance(call_kwargs["skill_ids"], list)
    assert isinstance(call_kwargs["memory_ids"], list)
    assert call_kwargs["snapshot_id"]
    assert call_kwargs["request_id"]


def test_context_snapshot_skipped_when_repo_is_none() -> None:
    """When no context snapshot repo is wired, generation completes normally."""
    app = create_app(_settings())
    app.dependency_overrides[get_optional_context_snapshot_repo] = lambda: None

    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.post(
            "/v1/generations",
            json=_generation_body(),
            headers={"Authorization": "Bearer admin-token"},
        )

    assert response.status_code == 200
