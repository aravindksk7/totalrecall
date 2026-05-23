"""Provider gateway: routes generation requests to the correct provider adapter."""

from totalrecall.errors import ServiceError, ServiceErrorCode
from totalrecall.providers.base import ProviderInterface
from totalrecall.providers.models import (
    ProviderHealth,
    ProviderHealthStatus,
    ProviderRequest,
    ProviderResponse,
)


class ProviderNotFoundError(Exception):
    pass


class ProviderGateway:
    """Routes ProviderRequest to the registered provider matching the config.provider_id."""

    def __init__(self, providers: dict[str, ProviderInterface]) -> None:
        self._providers = providers

    def generate(
        self,
        request: ProviderRequest,
        fallback_provider_ids: list[str] | None = None,
    ) -> ProviderResponse:
        """Generate using the primary provider, falling back to each listed alternative on ProviderNotFoundError."""
        chain = [request.config.provider_id] + (fallback_provider_ids or [])
        last_exc: ProviderNotFoundError | None = None
        for provider_id in chain:
            try:
                provider = self._resolve(provider_id)
                # Rebind request config so the provider sees its registered name
                if provider_id != request.config.provider_id:
                    from totalrecall.providers.models import ProviderConfig
                    request = request.model_copy(
                        update={"config": request.config.model_copy(update={"provider_id": provider_id})}
                    )
                response = provider.generate(request)
                # Normalize provider_id in response to the gateway's registered name
                if response.provider_id != provider_id:
                    response = response.model_copy(update={"provider_id": provider_id})
                return response
            except ProviderNotFoundError as exc:
                last_exc = exc
        raise last_exc  # type: ignore[misc]

    def health(self, provider_id: str) -> ProviderHealth:
        try:
            return self._resolve(provider_id).health()
        except ProviderNotFoundError:
            return ProviderHealth(
                provider_id=provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                error=ServiceError(
                    code=ServiceErrorCode.PROVIDER_UNAVAILABLE,
                    message=f"Provider '{provider_id}' is not registered",
                ),
            )

    def registered_ids(self) -> list[str]:
        return list(self._providers.keys())

    def _resolve(self, provider_id: str) -> ProviderInterface:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise ProviderNotFoundError(
                f"Provider '{provider_id}' is not registered. "
                f"Available: {sorted(self._providers)}"
            )
        return provider
