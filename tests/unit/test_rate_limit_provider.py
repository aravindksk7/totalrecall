"""Unit tests for RateLimitProvider sliding-window logic."""

import time

import pytest

from totalrecall.ratelimit.models import RateLimitPolicy
from totalrecall.ratelimit.provider import RateLimitProvider


def _provider(max_requests: int, window_seconds: int = 60) -> RateLimitProvider:
    return RateLimitProvider(
        default_policy=RateLimitPolicy(max_requests=max_requests, window_seconds=window_seconds)
    )


def test_first_request_is_allowed() -> None:
    provider = _provider(max_requests=5)
    result = provider.check("tenant_a")
    assert result.allowed is True


def test_remaining_decrements_per_request() -> None:
    provider = _provider(max_requests=3)
    r1 = provider.check("tenant_a")
    r2 = provider.check("tenant_a")
    assert r1.remaining == 2
    assert r2.remaining == 1


def test_request_denied_when_limit_reached() -> None:
    provider = _provider(max_requests=2)
    provider.check("tenant_a")
    provider.check("tenant_a")
    result = provider.check("tenant_a")
    assert result.allowed is False
    assert result.remaining == 0
    assert result.retry_after_seconds >= 1


def test_different_tenants_have_independent_buckets() -> None:
    provider = _provider(max_requests=1)
    r_a = provider.check("tenant_a")
    r_b = provider.check("tenant_b")
    assert r_a.allowed is True
    assert r_b.allowed is True


def test_per_tenant_policy_overrides_default() -> None:
    provider = RateLimitProvider(
        default_policy=RateLimitPolicy(max_requests=10, window_seconds=60),
        per_tenant={"tenant_premium": RateLimitPolicy(max_requests=100, window_seconds=60)},
    )
    # Standard tenant uses default
    for _ in range(10):
        provider.check("tenant_standard")
    assert provider.check("tenant_standard").allowed is False

    # Premium tenant has higher limit
    for _ in range(100):
        r = provider.check("tenant_premium")
        assert r.allowed is True


def test_from_config_builds_default_policy() -> None:
    provider = RateLimitProvider.from_config(
        {"default": {"max_requests": 2, "window_seconds": 60}}
    )
    provider.check("t1")
    provider.check("t1")
    assert provider.check("t1").allowed is False


def test_from_config_empty_dict_uses_built_in_default() -> None:
    provider = RateLimitProvider.from_config({})
    result = provider.check("tenant_x")
    assert result.allowed is True


def test_from_config_per_tenant_override() -> None:
    provider = RateLimitProvider.from_config(
        {
            "default": {"max_requests": 1, "window_seconds": 60},
            "tenant_vip": {"max_requests": 5, "window_seconds": 60},
        }
    )
    # default tenant gets 1 request
    provider.check("tenant_std")
    assert provider.check("tenant_std").allowed is False

    # vip tenant gets 5
    for _ in range(5):
        assert provider.check("tenant_vip").allowed is True
    assert provider.check("tenant_vip").allowed is False


def test_window_expires_and_allows_again() -> None:
    provider = RateLimitProvider(
        default_policy=RateLimitPolicy(max_requests=1, window_seconds=1)
    )
    assert provider.check("tenant_a").allowed is True
    assert provider.check("tenant_a").allowed is False
    time.sleep(1.1)
    assert provider.check("tenant_a").allowed is True
