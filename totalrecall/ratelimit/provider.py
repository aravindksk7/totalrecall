"""In-process sliding-window rate limiter.

Each tenant gets its own sliding-window bucket. Requests arriving after the
window has fully elapsed are unconditionally allowed. When a tenant_id has no
explicit policy the default policy applies.

Thread-safe: each bucket carries its own lock so contention is per-tenant.
"""

import threading
import time
from collections import deque

from totalrecall.ratelimit.models import RateLimitPolicy, RateLimitResult

_DEFAULT_POLICY = RateLimitPolicy(max_requests=60, window_seconds=60)


class _TenantBucket:
    def __init__(self, policy: RateLimitPolicy) -> None:
        self._policy = policy
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def check_and_record(self) -> RateLimitResult:
        now = time.monotonic()
        window_start = now - self._policy.window_seconds
        with self._lock:
            while self._timestamps and self._timestamps[0] < window_start:
                self._timestamps.popleft()

            count = len(self._timestamps)
            if count >= self._policy.max_requests:
                oldest = self._timestamps[0]
                retry_after = max(1, int(oldest - window_start) + 1)
                return RateLimitResult(allowed=False, remaining=0, retry_after_seconds=retry_after)

            self._timestamps.append(now)
            return RateLimitResult(
                allowed=True,
                remaining=self._policy.max_requests - count - 1,
            )


class RateLimitProvider:
    """Manages per-tenant sliding-window rate-limit buckets.

    Args:
        default_policy: Applied to any tenant without an explicit entry.
        per_tenant: Optional overrides keyed by tenant_id.
    """

    def __init__(
        self,
        default_policy: RateLimitPolicy = _DEFAULT_POLICY,
        per_tenant: dict[str, RateLimitPolicy] | None = None,
    ) -> None:
        self._default = default_policy
        self._policies = dict(per_tenant or {})
        self._buckets: dict[str, _TenantBucket] = {}
        self._buckets_lock = threading.Lock()

    def check(self, tenant_id: str) -> RateLimitResult:
        """Record one request for tenant_id and return whether it is allowed."""
        bucket = self._get_or_create_bucket(tenant_id)
        return bucket.check_and_record()

    def _get_or_create_bucket(self, tenant_id: str) -> _TenantBucket:
        with self._buckets_lock:
            if tenant_id not in self._buckets:
                policy = self._policies.get(tenant_id, self._default)
                self._buckets[tenant_id] = _TenantBucket(policy)
            return self._buckets[tenant_id]

    @classmethod
    def from_config(cls, config: dict[str, dict]) -> "RateLimitProvider":
        """Build from the Settings.rate_limits dict.

        Expected format::

            {
                "default": {"max_requests": 60, "window_seconds": 60},
                "tenant_premium": {"max_requests": 300, "window_seconds": 60},
            }
        """
        default_cfg = config.get("default", {})
        default_policy = (
            RateLimitPolicy(**default_cfg) if default_cfg else _DEFAULT_POLICY
        )
        per_tenant = {
            k: RateLimitPolicy(**v)
            for k, v in config.items()
            if k != "default"
        }
        return cls(default_policy=default_policy, per_tenant=per_tenant)
