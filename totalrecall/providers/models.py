from enum import StrEnum
from typing import Any

from pydantic import Field

from totalrecall.contracts import ContractModel
from totalrecall.errors import ServiceError


class ProviderRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ProviderFinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALL = "tool_call"
    ERROR = "error"
    UNKNOWN = "unknown"


class ProviderHealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ProviderMessage(ContractModel):
    role: ProviderRole
    content: str = Field(min_length=1)


class ProviderConfig(ContractModel):
    provider_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    timeout_seconds: int = Field(default=60, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class ProviderRequest(ContractModel):
    request_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    messages: list[ProviderMessage] = Field(min_length=1)
    config: ProviderConfig
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderUsage(ContractModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class ProviderResponse(ContractModel):
    request_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    raw_text: str
    usage: ProviderUsage = Field(default_factory=ProviderUsage)
    finish_reason: ProviderFinishReason = ProviderFinishReason.UNKNOWN
    errors: list[ServiceError] = Field(default_factory=list)
    latency_ms: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderHealth(ContractModel):
    provider_id: str = Field(min_length=1)
    status: ProviderHealthStatus
    model: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    error: ServiceError | None = None
