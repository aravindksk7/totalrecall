import os
from typing import Self
from urllib.request import Request

import pytest

from totalrecall.config.credentials import (
    CredentialNotFoundError,
    CredentialProviderChain,
    EnvLocalCredentialProvider,
    ExternalCredentialProvider,
)


class _Response:
    def __init__(self, body: str) -> None:
        self._body = body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body.encode("utf-8")


def test_env_credential_provider_reads_environment_value(tmp_path) -> None:
    os.environ["TOTALRECALL_TEST_SECRET"] = "secret-value"
    provider = EnvLocalCredentialProvider(
        credential_refs={"openai.api_key": "env:TOTALRECALL_TEST_SECRET"},
        local_secrets_dir=tmp_path,
    )

    assert provider.get("openai.api_key") == "secret-value"


def test_credential_provider_rejects_missing_reference(tmp_path) -> None:
    provider = EnvLocalCredentialProvider(credential_refs={}, local_secrets_dir=tmp_path)

    with pytest.raises(CredentialNotFoundError):
        provider.get("missing")


def test_env_local_credential_provider_reads_file_reference(tmp_path) -> None:
    secret_file = tmp_path / "openai_api_key"
    secret_file.write_text("file-secret\n", encoding="utf-8")
    provider = EnvLocalCredentialProvider(
        credential_refs={"openai.api_key": "file:openai_api_key"},
        local_secrets_dir=tmp_path,
    )

    assert provider.get("openai.api_key") == "file-secret"


def test_external_credential_provider_reads_json_value() -> None:
    calls: list[Request] = []

    def opener(request: Request, timeout: int) -> _Response:
        calls.append(request)
        assert timeout == 7
        return _Response('{"value": "cloud-secret"}')

    provider = ExternalCredentialProvider(
        credential_refs={"mem0_api_key": "cloud:projects/test/secrets/mem0"},
        base_url="https://secrets.example.test",
        auth_token="adapter-token",
        timeout_seconds=7,
        opener=opener,
    )

    assert provider.get("mem0_api_key") == "cloud-secret"
    assert calls[0].full_url.endswith("/secrets/projects%2Ftest%2Fsecrets%2Fmem0")
    assert calls[0].get_header("Authorization") == "Bearer adapter-token"


def test_external_credential_provider_reads_plaintext_value() -> None:
    provider = ExternalCredentialProvider(
        credential_refs={"api_key": "external:api-key"},
        base_url="https://secrets.example.test",
        opener=lambda request, timeout: _Response("plain-secret"),
    )

    assert provider.get("api_key") == "plain-secret"


def test_credential_provider_chain_falls_through_to_external(tmp_path) -> None:
    env_provider = EnvLocalCredentialProvider(
        credential_refs={"api_key": "external:api-key"},
        local_secrets_dir=tmp_path,
    )
    external_provider = ExternalCredentialProvider(
        credential_refs={"api_key": "external:api-key"},
        base_url="https://secrets.example.test",
        opener=lambda request, timeout: _Response('{"value": "from-external"}'),
    )
    chain = CredentialProviderChain([env_provider, external_provider])

    assert chain.get("api_key") == "from-external"
