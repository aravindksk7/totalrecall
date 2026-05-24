import subprocess

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


def _client_with_settings(settings: Settings):
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
    assert {
        "mem0_api_key",
        "mem0_host",
        "mem0_jwt_secret",
        "openai_api_key",
        "gemini_api_key",
        "anthropic_api_key",
    } <= keys
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


def test_admin_can_save_mem0_self_hosted_api_host(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.put(
            "/v1/credentials/mem0_host",
            json={"value": "http://localhost:8888"},
            headers={"Authorization": "Bearer admin-token"},
        )
        status_response = client.get(
            "/v1/credentials",
            headers={"Authorization": "Bearer admin-token"},
        )

    assert response.status_code == 200
    status_body = status_response.json()
    host_status = next(
        item for item in status_body["credentials"] if item["key"] == "mem0_host"
    )
    assert host_status["configured"] is True
    assert host_status["secret"] is False


def test_admin_can_configure_self_hosted_mem0_without_docker_start(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/v1/mem0/self-hosted/start",
            json={
                "openai_api_key": "openai-secret",
                "mem0_admin_api_key": "mem0-admin-secret",
                "mem0_jwt_secret": "jwt-secret-value-123",
                "mem0_host": "http://mem0:8000",
                "start_containers": True,
                "activate": True,
            },
            headers={"Authorization": "Bearer admin-token"},
        )
        flags_response = client.get(
            "/v1/flags",
            headers={"Authorization": "Bearer admin-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["started"] is False
    assert body["start_status"] == "disabled"
    assert body["mem0_host"] == "http://mem0:8000"
    assert "openai-secret" not in response.text
    assert "mem0-admin-secret" not in response.text
    assert "jwt-secret-value-123" not in response.text

    secrets_dir = tmp_path / "local-secrets"
    assert (secrets_dir / "openai_api_key").read_text(encoding="utf-8").strip() == "openai-secret"
    assert (secrets_dir / "mem0_api_key").read_text(encoding="utf-8").strip() == "mem0-admin-secret"
    jwt_secret = (secrets_dir / "mem0_jwt_secret").read_text(encoding="utf-8").strip()
    assert jwt_secret == "jwt-secret-value-123"
    env_file = (secrets_dir / "mem0-selfhost.env").read_text(encoding="utf-8")
    assert 'OPENAI_API_KEY="openai-secret"' in env_file
    assert 'MEM0_ADMIN_API_KEY="mem0-admin-secret"' in env_file
    assert 'MEM0_JWT_SECRET="jwt-secret-value-123"' in env_file
    flags = flags_response.json()["flags"]["values"]
    assert flags["memory.adapter"] == "mem0_v1"


def test_admin_can_start_self_hosted_mem0_when_docker_control_enabled(
    tmp_path,
    monkeypatch,
) -> None:
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "docker-compose.mem0.yml").write_text("services: {}\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_run(command, **kwargs):
        calls.append({"command": command, "cwd": kwargs["cwd"]})
        return subprocess.CompletedProcess(command, 0, stdout="started", stderr="")

    monkeypatch.setattr("totalrecall.selfhost.mem0.subprocess.run", fake_run)
    settings = Settings(
        environment="test",
        local_secrets_dir=tmp_path / "local-secrets",
        docker_compose_project_dir=tmp_path,
        admin_docker_control_enabled=True,
        auth_tokens={
            "admin-token": AuthTokenConfig(
                tenant_id="tenant_test",
                actor_id="actor_admin",
                roles=["admin"],
            ),
        },
        feature_flags={"memory.adapter": "stub"},
    )
    with _client_with_settings(settings) as client:
        response = client.post(
            "/v1/mem0/self-hosted/start",
            json={
                "openai_api_key": "openai-secret",
                "mem0_admin_api_key": "mem0-admin-secret",
                "mem0_jwt_secret": "jwt-secret-value-123",
                "mem0_host": "http://mem0:8000",
            },
            headers={"Authorization": "Bearer admin-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["started"] is True
    assert body["start_status"] == "started"
    assert calls
    command = calls[0]["command"]
    assert command[:2] == ["docker", "compose"]
    assert "docker-compose.mem0.yml" in command
    assert "mem0" in command
    assert calls[0]["cwd"] == tmp_path.resolve()


def test_reader_cannot_configure_self_hosted_mem0(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/v1/mem0/self-hosted/start",
            json={
                "openai_api_key": "openai-secret",
                "mem0_admin_api_key": "mem0-admin-secret",
                "mem0_jwt_secret": "jwt-secret-value-123",
                "mem0_host": "http://mem0:8000",
            },
            headers={"Authorization": "Bearer reader-token"},
        )

    assert response.status_code == 403


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
