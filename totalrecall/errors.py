from enum import StrEnum
from typing import Any

from pydantic import Field

from totalrecall.contracts import ContractModel


class ServiceErrorCode(StrEnum):
    VALIDATION_FAILED = "VALIDATION_FAILED"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    PROVIDER_AUTH_FAILED = "PROVIDER_AUTH_FAILED"
    MEMORY_UNAVAILABLE = "MEMORY_UNAVAILABLE"
    MEMORY_SCHEMA_MISMATCH = "MEMORY_SCHEMA_MISMATCH"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    GUARDRAIL_BLOCKED = "GUARDRAIL_BLOCKED"
    NORMALIZATION_FAILED = "NORMALIZATION_FAILED"


class ServiceError(ContractModel):
    code: ServiceErrorCode
    message: str = Field(min_length=1)
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
