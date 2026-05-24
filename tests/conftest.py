from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from totalrecall.auth.models import AuthTokenConfig
from totalrecall.config.settings import Settings
from totalrecall.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        environment="test",
        local_secrets_dir=tmp_path / "secrets",
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
        feature_flags={
            "memory.adapter": "stub",
            "memory.write_enabled": True,
            "memory.fail_open_on_search": True,
        },
    )


@pytest.fixture
def client(settings: Settings) -> Generator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
