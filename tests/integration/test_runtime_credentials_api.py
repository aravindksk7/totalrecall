from fastapi.testclient import TestClient

from totalrecall.auth.models import AuthTokenConfig
from totalrecall.config.settings import Settings
from totalrecall.main import create_app


def _client(tmp_path):
    settings = Settings(
        environment="test",
        local_secrets_dir=tmp_path / "local-secrets",
        auth_tokens={
            "admin-token": AuthTokenConfig(
                tenant_id="tenant_test",
                actor_id="actor_admin",
                roles=["admin"],
            ),
            "reader-token": AuthTokenConfig(
                tenant_id="tenant_test",
                actor_id="actor_reader",
                roles=["reader"],
            ),
        },
        feature_flags={"memory.adapter": "stub"},
    )
    return TestClient(create_app(settings))


def test_credentials_endpoint_lists_supported_credentials_without_values(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get(
            "/v1/credentials",
            headers={"Authorization": "Bearer admin-token"},
        )

    assert response.status_code == 200
    body = response.json()
    keys = {item["key"] for item in body["credentials"]}
    assert {"mem0_api_key", "openai_api_key", "gemini_api_key", "anthropic_api_key"} <= keys
    assert "secret-value" not in response.text


def test_reader_cannot_manage_runtime_credentials(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get(
            "/v1/credentials",
            headers={"Authorization": "Bearer reader-token"},
        )

    assert response.status_code == 403


def test_admin_can_save_credential_without_returning_secret(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.put(
            "/v1/credentials/openai_api_key",
            json={"value": "secret-value"},
            headers={"Authorization": "Bearer admin-token"},
        )
        status_response = client.get(
            "/v1/credentials",
            headers={"Authorization": "Bearer admin-token"},
        )

    assert response.status_code == 200
    assert "secret-value" not in response.text
    status_body = status_response.json()
    openai_status = next(
        item for item in status_body["credentials"] if item["key"] == "openai_api_key"
    )
    assert openai_status["configured"] is True
    assert openai_status["ref"] == "local:openai_api_key"


def test_saving_mem0_credential_can_activate_runtime_memory_flags(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.put(
            "/v1/credentials/mem0_api_key",
            json={"value": "mem0-secret", "activate": True},
            headers={"Authorization": "Bearer admin-token"},
        )
        flags_response = client.get(
            "/v1/flags",
            headers={"Authorization": "Bearer admin-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["activated"] is True
    flags = flags_response.json()["flags"]["values"]
    assert flags["memory.adapter"] == "mem0_v1"
    assert flags["memory.write_enabled"] is True


def test_admin_can_delete_runtime_credential(tmp_path) -> None:
    with _client(tmp_path) as client:
        client.put(
            "/v1/credentials/openai_api_key",
            json={"value": "secret-value"},
            headers={"Authorization": "Bearer admin-token"},
        )
        response = client.delete(
            "/v1/credentials/openai_api_key",
            headers={"Authorization": "Bearer admin-token"},
        )
        status_response = client.get(
            "/v1/credentials",
            headers={"Authorization": "Bearer admin-token"},
        )

    assert response.status_code == 200
    status_body = status_response.json()
    openai_status = next(
        item for item in status_body["credentials"] if item["key"] == "openai_api_key"
    )
    assert openai_status["configured"] is False
