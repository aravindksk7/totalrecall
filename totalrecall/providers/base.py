from abc import ABC, abstractmethod

from totalrecall.providers.models import ProviderHealth, ProviderRequest, ProviderResponse


class ProviderInterface(ABC):
    """Common contract for all LLM provider adapters."""

    @property
    @abstractmethod
    def provider_id(self) -> str: ...

    @abstractmethod
    def generate(self, request: ProviderRequest) -> ProviderResponse: ...

    @abstractmethod
    def health(self) -> ProviderHealth: ...
