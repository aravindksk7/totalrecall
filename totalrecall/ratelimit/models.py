"""Rate-limit policy and result models."""

from pydantic import Field

from totalrecall.contracts import ContractModel


class RateLimitPolicy(ContractModel):
    max_requests: int = Field(ge=1, description="Maximum requests allowed within the window.")
    window_seconds: int = Field(ge=1, description="Window duration in seconds.")


class RateLimitResult(ContractModel):
    allowed: bool
    remaining: int = Field(ge=0)
    retry_after_seconds: int = Field(ge=0, default=0)
