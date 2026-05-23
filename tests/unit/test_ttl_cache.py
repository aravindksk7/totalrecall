"""Unit tests for TTLCache and cache key helpers."""

import time

import pytest

from totalrecall.cache.provider import (
    TTLCache,
    build_search_cache_key,
    search_invalidation_prefix,
)


def test_get_returns_none_for_missing_key() -> None:
    cache = TTLCache(ttl_seconds=60)
    assert cache.get("no_such_key") is None


def test_set_and_get_returns_value() -> None:
    cache = TTLCache(ttl_seconds=60)
    cache.set("k", "hello")
    assert cache.get("k") == "hello"


def test_stores_arbitrary_objects() -> None:
    cache = TTLCache(ttl_seconds=60)
    obj = {"items": [1, 2, 3], "meta": True}
    cache.set("obj", obj)
    assert cache.get("obj") == obj


def test_entry_expires_after_ttl() -> None:
    cache = TTLCache(ttl_seconds=1)
    cache.set("exp", "gone_soon")
    time.sleep(1.1)
    assert cache.get("exp") is None


def test_size_counts_live_entries() -> None:
    cache = TTLCache(ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.size == 2


def test_size_excludes_expired_entries() -> None:
    cache = TTLCache(ttl_seconds=1)
    cache.set("exp_a", 1)
    cache.set("live_b", 2)
    time.sleep(1.1)
    # Set a live entry after expiry
    cache.set("live_b", 2)
    assert cache.size == 1


def test_clear_empties_cache() -> None:
    cache = TTLCache(ttl_seconds=60)
    cache.set("x", 1)
    cache.set("y", 2)
    cache.clear()
    assert cache.size == 0
    assert cache.get("x") is None


def test_invalidate_prefix_removes_matching_keys() -> None:
    cache = TTLCache(ttl_seconds=60)
    cache.set("msearch:tenant_a:app1:abc", "result1")
    cache.set("msearch:tenant_a:app1:def", "result2")
    cache.set("msearch:tenant_b:app1:abc", "other")
    removed = cache.invalidate_prefix("msearch:tenant_a:app1:")
    assert removed == 2
    assert cache.get("msearch:tenant_a:app1:abc") is None
    assert cache.get("msearch:tenant_b:app1:abc") == "other"


def test_invalidate_prefix_returns_zero_when_no_match() -> None:
    cache = TTLCache(ttl_seconds=60)
    cache.set("msearch:tenant_a:app1:abc", "result")
    removed = cache.invalidate_prefix("msearch:tenant_z:")
    assert removed == 0


# --- cache key helpers ---

def test_build_search_cache_key_is_stable() -> None:
    k1 = build_search_cache_key("t", "a", "query", {"domain": "auth"}, 10)
    k2 = build_search_cache_key("t", "a", "query", {"domain": "auth"}, 10)
    assert k1 == k2


def test_build_search_cache_key_differs_by_query() -> None:
    k1 = build_search_cache_key("t", "a", "login page", {}, 10)
    k2 = build_search_cache_key("t", "a", "checkout page", {}, 10)
    assert k1 != k2


def test_build_search_cache_key_differs_by_tenant() -> None:
    k1 = build_search_cache_key("tenant_a", "app", "q", {}, 10)
    k2 = build_search_cache_key("tenant_b", "app", "q", {}, 10)
    assert k1 != k2


def test_build_search_cache_key_has_expected_prefix() -> None:
    k = build_search_cache_key("t1", "a1", "q", {}, 10)
    assert k.startswith("msearch:t1:a1:")


def test_search_invalidation_prefix_format() -> None:
    prefix = search_invalidation_prefix("tenant_x", "app_y")
    assert prefix == "msearch:tenant_x:app_y:"
