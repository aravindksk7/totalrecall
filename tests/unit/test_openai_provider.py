"""Unit tests for OpenAIProvider — mocks the openai package entirely."""

import sys
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from totalrecall.providers.models import (
    ProviderConfig,
    ProviderFinishReason,
    ProviderHealthStatus,
    ProviderMessage,
    ProviderRequest,
    ProviderRole,
)


def _make_credential_provider(api_key: str = "sk-test") -> MagicMock:
    provider = MagicMock()
    provider.get.return_value = api_key
    return provider


def _make_request(request_id: str = "req_001") -> ProviderRequest:
    return ProviderRequest(
        request_id=request_id,
        tenant_id="tenant_test",
        messages=[
            ProviderMessage(role=ProviderRole.SYSTEM, content="You are a test generator."),
            ProviderMessage(role=ProviderRole.USER, content="Write a page object."),
        ],
        config=ProviderConfig(provider_id="openai", model="gpt-4o"),
    )


def _fake_openai_module(finish_reason: str = "stop", content: str = '{"artifacts":[]}') -> Any:
    """Build a minimal fake openai module that satisfies OpenAIProvider._get_client()."""
    choice = MagicMock()
    choice.finish_reason = finish_reason
    choice.message.content = content

    usage = MagicMock()
    usage.prompt_tokens = 42
    usage.completion_tokens = 17

    completion = MagicMock()
    completion.choices = [choice]
    completion.usage = usage
    completion.model = "gpt-4o"

    client_instance = MagicMock()
    client_instance.chat.completions.create.return_value = completion
    client_instance.models.list.return_value = []

    openai_mod = ModuleType("openai")
    openai_mod.OpenAI = MagicMock(return_value=client_instance)  # type: ignore[attr-defined]
    return openai_mod


@pytest.fixture(autouse=True)
def _unload_openai():
    """Ensure openai is not cached between tests."""
    yield
    sys.modules.pop("openai", None)


def test_generate_returns_response_with_correct_request_id() -> None:
    with patch.dict(sys.modules, {"openai": _fake_openai_module()}):
        from totalrecall.providers.openai.provider import OpenAIProvider

        provider = OpenAIProvider(_make_credential_provider())
        response = provider.generate(_make_request("req_xyz"))

    assert response.request_id == "req_xyz"


def test_generate_maps_stop_finish_reason() -> None:
    with patch.dict(sys.modules, {"openai": _fake_openai_module(finish_reason="stop")}):
        from totalrecall.providers.openai.provider import OpenAIProvider

        provider = OpenAIProvider(_make_credential_provider())
        response = provider.generate(_make_request())

    assert response.finish_reason == ProviderFinishReason.STOP


def test_generate_maps_length_finish_reason() -> None:
    with patch.dict(sys.modules, {"openai": _fake_openai_module(finish_reason="length")}):
        from totalrecall.providers.openai.provider import OpenAIProvider

        provider = OpenAIProvider(_make_credential_provider())
        response = provider.generate(_make_request())

    assert response.finish_reason == ProviderFinishReason.LENGTH


def test_generate_maps_unknown_finish_reason() -> None:
    with patch.dict(sys.modules, {"openai": _fake_openai_module(finish_reason="content_filter")}):
        from totalrecall.providers.openai.provider import OpenAIProvider

        provider = OpenAIProvider(_make_credential_provider())
        response = provider.generate(_make_request())

    assert response.finish_reason == ProviderFinishReason.UNKNOWN


def test_generate_populates_token_usage() -> None:
    with patch.dict(sys.modules, {"openai": _fake_openai_module()}):
        from totalrecall.providers.openai.provider import OpenAIProvider

        provider = OpenAIProvider(_make_credential_provider())
        response = provider.generate(_make_request())

    assert response.usage.input_tokens == 42
    assert response.usage.output_tokens == 17


def test_generate_returns_raw_text_from_choice() -> None:
    content = '{"artifacts": []}'
    with patch.dict(sys.modules, {"openai": _fake_openai_module(content=content)}):
        from totalrecall.providers.openai.provider import OpenAIProvider

        provider = OpenAIProvider(_make_credential_provider())
        response = provider.generate(_make_request())

    assert response.raw_text == content


def test_generate_returns_error_response_on_api_exception() -> None:
    fake_mod = _fake_openai_module()
    client_instance = fake_mod.OpenAI.return_value
    client_instance.chat.completions.create.side_effect = RuntimeError("API error")

    with patch.dict(sys.modules, {"openai": fake_mod}):
        from totalrecall.providers.openai.provider import OpenAIProvider

        provider = OpenAIProvider(_make_credential_provider())
        response = provider.generate(_make_request())

    assert response.finish_reason == ProviderFinishReason.ERROR
    assert len(response.errors) == 1
    assert "API error" in response.errors[0].message


def test_generate_records_positive_latency_ms() -> None:
    with patch.dict(sys.modules, {"openai": _fake_openai_module()}):
        from totalrecall.providers.openai.provider import OpenAIProvider

        provider = OpenAIProvider(_make_credential_provider())
        response = provider.generate(_make_request())

    assert response.latency_ms >= 0


def test_provider_id_is_openai() -> None:
    with patch.dict(sys.modules, {"openai": _fake_openai_module()}):
        from totalrecall.providers.openai.provider import OpenAIProvider

        provider = OpenAIProvider(_make_credential_provider())

    assert provider.provider_id == "openai"


def test_health_returns_ok_when_api_responds() -> None:
    with patch.dict(sys.modules, {"openai": _fake_openai_module()}):
        from totalrecall.providers.openai.provider import OpenAIProvider

        provider = OpenAIProvider(_make_credential_provider())
        health = provider.health()

    assert health.status == ProviderHealthStatus.OK
    assert health.provider_id == "openai"


def test_health_returns_unavailable_when_api_raises() -> None:
    fake_mod = _fake_openai_module()
    client_instance = fake_mod.OpenAI.return_value
    client_instance.models.list.side_effect = RuntimeError("network error")

    with patch.dict(sys.modules, {"openai": fake_mod}):
        from totalrecall.providers.openai.provider import OpenAIProvider

        provider = OpenAIProvider(_make_credential_provider())
        health = provider.health()

    assert health.status == ProviderHealthStatus.UNAVAILABLE


def test_health_returns_unavailable_when_openai_not_installed() -> None:
    with patch.dict(sys.modules, {"openai": None}):  # type: ignore[dict-item]
        # Remove cached module reference so import fails
        sys.modules.pop("totalrecall.providers.openai.provider", None)
        from totalrecall.providers.openai.provider import OpenAIProvider

        provider = OpenAIProvider(_make_credential_provider())
        health = provider.health()

    assert health.status == ProviderHealthStatus.UNAVAILABLE
