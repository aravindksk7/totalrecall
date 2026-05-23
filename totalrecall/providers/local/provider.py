"""Local provider adapter placeholder for Ollama-compatible local LLM servers.

This module defines the boundary for local/self-hosted LLM adapters. The full
implementation is deferred to post-MVP; this placeholder exposes the interface
and raises a clear error so callers get a meaningful message instead of a
missing-module import error.

To implement: replace `NotImplementedError` in `generate` with an actual HTTP
call to the Ollama-compatible endpoint (default http://localhost:11434/api/generate).
"""

from totalrecall.providers.base import ProviderInterface
from totalrecall.providers.models import (
    ProviderHealth,
    ProviderHealthStatus,
    ProviderRequest,
    ProviderResponse,
)


class LocalProvider(ProviderInterface):
    """Placeholder for an Ollama-compatible local LLM adapter.

    Registered as provider_id ``local``. The gateway can route requests here,
    and a ``fallback_provider_ids`` chain can fall through to a real provider
    until this implementation is complete.
    """

    _PROVIDER_ID = "local"

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3") -> None:
        self._base_url = base_url
        self._model = model

    @property
    def provider_id(self) -> str:
        return self._PROVIDER_ID

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError(
            "LocalProvider is a placeholder. "
            "Configure a real Ollama endpoint or use fallback_provider_ids to route elsewhere."
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_id=self._PROVIDER_ID,
            status=ProviderHealthStatus.UNAVAILABLE,
            model=self._model,
        )
