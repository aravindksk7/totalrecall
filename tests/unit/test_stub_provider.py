import json

from totalrecall.providers.models import (
    ProviderConfig,
    ProviderFinishReason,
    ProviderHealthStatus,
    ProviderMessage,
    ProviderRequest,
    ProviderRole,
)
from totalrecall.providers.stub.provider import StubProvider


def _make_request(request_id: str = "req_001") -> ProviderRequest:
    return ProviderRequest(
        request_id=request_id,
        tenant_id="tenant_test",
        messages=[
            ProviderMessage(role=ProviderRole.SYSTEM, content="You are a test generator."),
            ProviderMessage(role=ProviderRole.USER, content="Generate a page object."),
        ],
        config=ProviderConfig(provider_id="stub", model="stub"),
    )


def test_stub_provider_returns_deterministic_json_artifact() -> None:
    provider = StubProvider()
    response = provider.generate(_make_request())

    payload = json.loads(response.raw_text)
    assert "artifacts" in payload
    assert len(payload["artifacts"]) >= 1
    artifact = payload["artifacts"][0]
    assert "path" in artifact
    assert "content" in artifact


def test_stub_provider_echoes_request_id() -> None:
    provider = StubProvider()
    response = provider.generate(_make_request("req_xyz"))

    assert response.request_id == "req_xyz"


def test_stub_provider_reports_stop_finish_reason() -> None:
    provider = StubProvider()
    response = provider.generate(_make_request())

    assert response.finish_reason == ProviderFinishReason.STOP


def test_stub_provider_populates_token_usage() -> None:
    provider = StubProvider()
    response = provider.generate(_make_request())

    assert response.usage.input_tokens > 0
    assert response.usage.output_tokens > 0


def test_stub_provider_accepts_custom_fixed_response() -> None:
    custom = {
        "artifacts": [
            {
                "path": "x.ts",
                "artifact_type": "page_object",
                "language": "typescript",
                "content": "class X {}",
            }
        ]
    }
    provider = StubProvider(fixed_response=custom)
    response = provider.generate(_make_request())

    payload = json.loads(response.raw_text)
    assert payload["artifacts"][0]["path"] == "x.ts"


def test_stub_provider_health_is_ok() -> None:
    provider = StubProvider()
    health = provider.health()

    assert health.status == ProviderHealthStatus.OK
    assert health.provider_id == "stub"


def test_stub_provider_id_is_stub() -> None:
    provider = StubProvider()
    assert provider.provider_id == "stub"


def test_stub_provider_zero_latency() -> None:
    provider = StubProvider()
    response = provider.generate(_make_request())

    assert response.latency_ms == 0
