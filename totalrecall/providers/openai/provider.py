"""OpenAI provider adapter — isolated behind ProviderInterface.

Lazily imports the `openai` package so the rest of the service has no hard dependency on it.
Install with: uv add openai
"""

import time
from typing import Any

from totalrecall.config.credentials import EnvLocalCredentialProvider
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

_OPENAI_NOT_INSTALLED = (
    "The 'openai' package is required to use OpenAIProvider. "
    "Install it with: uv add openai"
)


class OpenAIProvider(ProviderInterface):
    """Sends generation requests to OpenAI's chat completions API.

    API key is resolved via CredentialProvider using the credential reference
    stored in settings.credential_refs['openai_api_key'].
    """

    _PROVIDER_ID = "openai"

    def __init__(
        self,
        credential_provider: EnvLocalCredentialProvider,
        credential_ref: str = "openai_api_key",
    ) -> None:
        self._credential_provider = credential_provider
        self._credential_ref = credential_ref
        self._client: Any = None

    @property
    def provider_id(self) -> str:
        return self._PROVIDER_ID

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import openai  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(_OPENAI_NOT_INSTALLED) from exc

        api_key = self._credential_provider.get(self._credential_ref)
        self._client = openai.OpenAI(api_key=api_key)
        return self._client

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        client = self._get_client()
        messages = [{"role": m.role.value, "content": m.content} for m in request.messages]

        kwargs: dict[str, Any] = {
            "model": request.config.model,
            "messages": messages,
            "temperature": request.config.temperature,
            "timeout": request.config.timeout_seconds,
        }
        if request.config.max_output_tokens:
            kwargs["max_tokens"] = request.config.max_output_tokens

        t0 = time.monotonic()
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            return ProviderResponse(
                request_id=request.request_id,
                provider_id=self._PROVIDER_ID,
                model=request.config.model,
                raw_text="",
                finish_reason=ProviderFinishReason.ERROR,
                latency_ms=latency_ms,
                errors=[
                    ServiceError(
                        code=ServiceErrorCode.PROVIDER_UNAVAILABLE,
                        message=str(exc),
                        retryable=True,
                    )
                ],
            )

        latency_ms = int((time.monotonic() - t0) * 1000)
        choice = response.choices[0]
        finish_map = {
            "stop": ProviderFinishReason.STOP,
            "length": ProviderFinishReason.LENGTH,
            "tool_calls": ProviderFinishReason.TOOL_CALL,
        }
        finish_reason = finish_map.get(choice.finish_reason or "", ProviderFinishReason.UNKNOWN)
        usage = response.usage
        return ProviderResponse(
            request_id=request.request_id,
            provider_id=self._PROVIDER_ID,
            model=response.model,
            raw_text=choice.message.content or "",
            usage=ProviderUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
            finish_reason=finish_reason,
            latency_ms=latency_ms,
        )

    def health(self) -> ProviderHealth:
        try:
            client = self._get_client()
        except ImportError as exc:
            return ProviderHealth(
                provider_id=self._PROVIDER_ID,
                status=ProviderHealthStatus.UNAVAILABLE,
                error=ServiceError(
                    code=ServiceErrorCode.PROVIDER_UNAVAILABLE,
                    message=str(exc),
                ),
            )
        try:
            t0 = time.monotonic()
            client.models.list()
            latency_ms = int((time.monotonic() - t0) * 1000)
            return ProviderHealth(
                provider_id=self._PROVIDER_ID,
                status=ProviderHealthStatus.OK,
                model=None,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            return ProviderHealth(
                provider_id=self._PROVIDER_ID,
                status=ProviderHealthStatus.UNAVAILABLE,
                error=ServiceError(
                    code=ServiceErrorCode.PROVIDER_UNAVAILABLE,
                    message=str(exc),
                ),
            )
