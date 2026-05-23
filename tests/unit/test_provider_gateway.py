"""Unit tests for ProviderGateway routing and fallback policy."""

import pytest

from totalrecall.providers.gateway import ProviderGateway, ProviderNotFoundError
from totalrecall.providers.models import (
    ProviderConfig,
    ProviderFinishReason,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderMessage,
    ProviderRequest,
    ProviderResponse,
    ProviderRole,
    ProviderUsage,
)
from totalrecall.providers.stub.provider import StubProvider


def _request(provider_id: str = "stub") -> ProviderRequest:
    return ProviderRequest(
        request_id="req_001",
        tenant_id="tenant_test",
        messages=[ProviderMessage(role=ProviderRole.USER, content="Generate something.")],
        config=ProviderConfig(provider_id=provider_id, model="test"),
    )


def _make_gateway(*provider_ids: str) -> ProviderGateway:
    return ProviderGateway(providers={pid: StubProvider() for pid in provider_ids})


# --- Basic routing ---


def test_gateway_routes_to_registered_provider() -> None:
    gateway = _make_gateway("stub")
    response = gateway.generate(_request("stub"))
    assert response.provider_id == "stub"


def test_gateway_raises_for_unknown_provider() -> None:
    gateway = _make_gateway("stub")
    with pytest.raises(ProviderNotFoundError):
        gateway.generate(_request("openai"))


def test_gateway_registered_ids_lists_all_providers() -> None:
    gateway = _make_gateway("stub", "openai")
    assert set(gateway.registered_ids()) == {"stub", "openai"}


def test_gateway_health_returns_unavailable_for_unknown() -> None:
    gateway = _make_gateway("stub")
    result = gateway.health("missing")
    assert result.status == ProviderHealthStatus.UNAVAILABLE


# --- Fallback policy ---


def test_fallback_used_when_primary_not_found() -> None:
    """Primary 'openai' is not registered; fallback 'stub' is used."""
    gateway = _make_gateway("stub")
    response = gateway.generate(_request("openai"), fallback_provider_ids=["stub"])
    assert response.provider_id == "stub"


def test_fallback_not_used_when_primary_succeeds() -> None:
    """Primary 'stub' is registered and succeeds — fallback should not be invoked."""
    gateway = _make_gateway("stub", "secondary")
    response = gateway.generate(_request("stub"), fallback_provider_ids=["secondary"])
    assert response.provider_id == "stub"


def test_multiple_fallbacks_tried_in_order() -> None:
    """Only 'third' is registered; should be reached after two missing primaries."""
    gateway = _make_gateway("third")
    response = gateway.generate(
        _request("first"), fallback_provider_ids=["second", "third"]
    )
    assert response.provider_id == "third"


def test_all_fallbacks_exhausted_raises_error() -> None:
    """No provider in the chain is registered — ProviderNotFoundError is raised."""
    gateway = _make_gateway("stub")
    with pytest.raises(ProviderNotFoundError):
        gateway.generate(_request("a"), fallback_provider_ids=["b", "c"])


def test_no_fallbacks_behaves_identically_to_before() -> None:
    """Passing an empty fallback list is equivalent to no fallback (original behaviour)."""
    gateway = _make_gateway("stub")
    response = gateway.generate(_request("stub"), fallback_provider_ids=[])
    assert response.provider_id == "stub"


def test_fallback_config_carries_through_to_response() -> None:
    """When a fallback provider is used, its provider_id appears in the response."""
    gateway = _make_gateway("backup")
    response = gateway.generate(_request("primary"), fallback_provider_ids=["backup"])
    assert response.provider_id == "backup"
