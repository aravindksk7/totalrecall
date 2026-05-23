"""Local provider adapter for Ollama-compatible local LLM servers."""

import time

from totalrecall.config.credentials import CredentialNotFoundError, CredentialProvider
from totalrecall.errors import ServiceError, ServiceErrorCode
from totalrecall.providers.base import ProviderInterface
from totalrecall.providers.models import (
    ProviderFinishReason,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)


class LocalProvider(ProviderInterface):
    """Ollama-compatible local LLM adapter registered as provider_id ``local``."""

    _PROVIDER_ID = "local"

    def __init__(
        self,
        credential_provider: CredentialProvider | None = None,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
    ) -> None:
        self._credential_provider = credential_provider
        self._base_url = base_url
        self._model = model

    @property
    def provider_id(self) -> str:
        return self._PROVIDER_ID

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        import httpx

        prompt = "\n\n".join(
            f"{message.role.value}: {message.content}" for message in request.messages
        )
        payload = {
            "model": request.config.model or self._model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": request.config.temperature},
        }
        headers = self._headers()
        started = time.monotonic()
        try:
            response = httpx.post(
                f"{self._resolved_base_url()}/api/generate",
                json=payload,
                headers=headers,
                timeout=request.config.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            return ProviderResponse(
                request_id=request.request_id,
                provider_id=self._PROVIDER_ID,
                model=request.config.model or self._model,
                raw_text="",
                finish_reason=ProviderFinishReason.ERROR,
                latency_ms=int((time.monotonic() - started) * 1000),
                errors=[
                    ServiceError(
                        code=ServiceErrorCode.PROVIDER_UNAVAILABLE,
                        message=str(exc),
                        retryable=True,
                    )
                ],
            )

        raw_text = str(data.get("response") or "")
        return ProviderResponse(
            request_id=request.request_id,
            provider_id=self._PROVIDER_ID,
            model=str(data.get("model") or request.config.model or self._model),
            raw_text=raw_text,
            usage=ProviderUsage(
                input_tokens=len(prompt.split()),
                output_tokens=len(raw_text.split()),
            ),
            finish_reason=ProviderFinishReason.STOP,
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    def health(self) -> ProviderHealth:
        import httpx

        try:
            started = time.monotonic()
            response = httpx.get(
                f"{self._resolved_base_url()}/api/tags",
                headers=self._headers(),
                timeout=3,
            )
            latency_ms = int((time.monotonic() - started) * 1000)
            status = (
                ProviderHealthStatus.OK
                if response.is_success
                else ProviderHealthStatus.DEGRADED
            )
            return ProviderHealth(
                provider_id=self._PROVIDER_ID,
                status=status,
                model=self._model,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            return ProviderHealth(
                provider_id=self._PROVIDER_ID,
                status=ProviderHealthStatus.UNAVAILABLE,
                model=self._model,
                error=ServiceError(
                    code=ServiceErrorCode.PROVIDER_UNAVAILABLE,
                    message=str(exc),
                    retryable=True,
                ),
            )

    def _resolved_base_url(self) -> str:
        if self._credential_provider is None:
            return self._base_url.rstrip("/")
        try:
            return self._credential_provider.get("local_llm_base_url").rstrip("/")
        except CredentialNotFoundError:
            return self._base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        if self._credential_provider is None:
            return {}
        try:
            token = self._credential_provider.get("local_llm_api_key")
        except CredentialNotFoundError:
            return {}
        return {"Authorization": f"Bearer {token}"}
