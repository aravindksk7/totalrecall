"""Live integration tests for the mem0_v1 adapter.

These tests require the self-hosted mem0 service to be running at
http://localhost:8888 (via docker-compose.mem0.yml).  They are
automatically skipped when the service is not reachable.
"""

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from totalrecall.auth.models import AuthTokenConfig
from totalrecall.config.settings import Settings
from totalrecall.main import create_app

_MEM0_HOST = "http://localhost:8888"
_LOCAL_SECRETS = Path(__file__).resolve().parents[2] / "local-secrets"


def _mem0_reachable() -> bool:
    try:
        r = httpx.get(f"{_MEM0_HOST}/auth/setup-status", timeout=3)
        return r.status_code < 500
    except Exception:
        return False


def _has_api_key() -> bool:
    return (_LOCAL_SECRETS / "mem0_api_key").is_file()


_SKIP_LIVE = pytest.mark.skipif(
    not (_mem0_reachable() and _has_api_key()),
    reason="mem0 service not reachable at localhost:8888 or mem0_api_key not configured",
)


def _live_settings() -> Settings:
    return Settings(
        environment="test",
        enable_database=False,
        local_secrets_dir=_LOCAL_SECRETS,
        credential_refs={
            "mem0_api_key": "local:mem0_api_key",
            "mem0_host": "env:MEM0_HOST",
        },
        auth_tokens={
            "admin-token": AuthTokenConfig(
                tenant_id="tenant_test",
                actor_id="actor_admin",
                roles=["admin"],
            ),
        },
        feature_flags={
            "memory.adapter": "mem0_v1",
            "memory.write_enabled": True,
            "memory.fail_open_on_search": True,
        },
    )


def _live_settings_env_host() -> Settings:
    """Settings variant that resolves mem0_host from env var MEM0_HOST."""
    return Settings(
        environment="test",
        enable_database=False,
        local_secrets_dir=_LOCAL_SECRETS,
        credential_refs={
            "mem0_api_key": "local:mem0_api_key",
            "mem0_host": "env:MEM0_HOST",
        },
        auth_tokens={
            "admin-token": AuthTokenConfig(
                tenant_id="tenant_test",
                actor_id="actor_admin",
                roles=["admin"],
            ),
        },
        feature_flags={
            "memory.adapter": "mem0_v1",
            "memory.write_enabled": True,
            "memory.fail_open_on_search": True,
        },
    )


_ADMIN_HEADERS = {"Authorization": "Bearer admin-token"}


# ---------------------------------------------------------------------------
# Settings unit tests (no live service required)
# ---------------------------------------------------------------------------


def test_settings_default_adapter_is_mem0_v1() -> None:
    s = Settings(
        environment="test",
        enable_database=False,
        auth_tokens={},
    )
    assert s.feature_flags["memory.adapter"] == "mem0_v1"


def test_settings_credential_refs_use_env_for_mem0_host() -> None:
    s = Settings(
        environment="test",
        enable_database=False,
        auth_tokens={},
    )
    assert s.credential_refs["mem0_host"] == "env:MEM0_HOST"


def test_settings_credential_refs_use_local_for_mem0_api_key() -> None:
    s = Settings(
        environment="test",
        enable_database=False,
        auth_tokens={},
    )
    assert s.credential_refs["mem0_api_key"] == "local:mem0_api_key"


def test_settings_write_enabled_and_fail_open_by_default() -> None:
    s = Settings(environment="test", enable_database=False, auth_tokens={})
    assert s.feature_flags.get("memory.write_enabled") is True
    assert s.feature_flags.get("memory.fail_open_on_search") is True


# ---------------------------------------------------------------------------
# Live adapter tests (skipped unless mem0 is running)
# ---------------------------------------------------------------------------


@pytest.fixture
def live_client(monkeypatch):
    monkeypatch.setenv("MEM0_HOST", _MEM0_HOST)
    with TestClient(create_app(_live_settings())) as client:
        yield client


@_SKIP_LIVE
def test_mem0_v1_adapter_health_reports_ok_with_live_credentials(live_client) -> None:
    response = live_client.get("/v1/monitoring/memory", headers=_ADMIN_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["active_adapter"] == "mem0_v1"
    assert body["configured_adapter"] == "mem0_v1"
    assert body["health"]["status"] == "ok"
    assert body["health"]["degraded"] is False


@_SKIP_LIVE
def test_mem0_v1_adapter_health_ok_with_env_host_credential(monkeypatch) -> None:
    monkeypatch.setenv("MEM0_HOST", _MEM0_HOST)
    with TestClient(create_app(_live_settings_env_host())) as client:
        response = client.get("/v1/monitoring/memory", headers=_ADMIN_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["health"]["status"] == "ok"
    assert body["health"]["degraded"] is False


@_SKIP_LIVE
def test_mem0_v1_monitoring_summary_shows_live_adapter(live_client) -> None:
    response = live_client.get("/v1/monitoring/summary", headers=_ADMIN_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["memory"]["active_adapter"] == "mem0_v1"
    assert body["memory"]["health"]["status"] == "ok"
    assert body["memory"]["mem0"]["credential_configured"] is True
    # host_configured reflects the file-based runtime store; env:MEM0_HOST is not file-based
    assert body["memory"]["mem0"]["host_configured"] is False
    assert body["memory"]["mem0"]["active"] is True


@_SKIP_LIVE
def test_mem0_v1_adapter_capabilities_report_delete_support(live_client) -> None:
    response = live_client.get("/v1/monitoring/memory", headers=_ADMIN_HEADERS)

    assert response.status_code == 200
    body = response.json()
    caps = body["capabilities"]
    assert caps["adapter_version"] == "mem0_v1"
    assert caps["supports_delete"] is True
    assert caps["supports_search"] is True
    assert caps["supports_upsert"] is True
    assert caps["supports_get"] is True


@_SKIP_LIVE
def test_mem0_v1_monitoring_memory_provider_reports_sdk_available(live_client) -> None:
    response = live_client.get("/v1/monitoring/memory", headers=_ADMIN_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["mem0"]["sdk_available"] is True
    assert body["mem0"]["write_enabled"] is True
    assert body["mem0"]["fail_open_on_search"] is True
    assert body["mem0"]["supports_search"] is True
    assert body["mem0"]["supports_delete"] is True
