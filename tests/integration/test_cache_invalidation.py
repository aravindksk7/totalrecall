"""Integration tests: cache is populated by memory search and invalidated on delete."""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from totalrecall.api.dependencies import get_audit_repo, get_tombstone_filter, get_tombstone_repo
from totalrecall.auth.models import AuthTokenConfig
from totalrecall.cache.provider import TTLCache, build_search_cache_key
from totalrecall.config.settings import Settings
from totalrecall.main import create_app
from totalrecall.memory.adapters.stub import StubMemoryAdapter
from totalrecall.memory.models import MemoryEntry
from totalrecall.memory.tombstone import TombstoneFilter


def _settings() -> Settings:
    return Settings(
        environment="test",
        enable_database=False,
        auth_tokens={
            "admin-token": AuthTokenConfig(
                tenant_id="tenant_cache",
                actor_id="actor_admin",
                roles=["admin"],
            ),
        },
        feature_flags={"memory.adapter": "stub"},
        cache_ttl_seconds=300,
    )


def _stub_entry(entity_id: str = "mem_login") -> MemoryEntry:
    return MemoryEntry(
        entity_id=entity_id,
        tenant_id="tenant_cache",
        application_id="app_cache",
        summary="Login page memory",
        knowledge="Use the LoginPage POM class",
        tags={},
    )


def test_memory_search_populates_cache() -> None:
    """After a search, the result is stored in the cache."""
    entry = _stub_entry()
    app = create_app(_settings())
    # Replace stub adapter with one that has a known entry
    app.state.memory_wrapper._adapters["stub"] = StubMemoryAdapter([entry])
    cache: TTLCache = app.state.cache

    with TestClient(app) as client:
        client.post(
            "/v1/generations",
            json={
                "tenant_id": "tenant_cache",
                "application_id": "app_cache",
                "prompt": "Generate a login page object",
                "target": {"language": "typescript", "framework": "playwright", "pattern": "pom", "locator_strategy": "page_file"},
                "scope": {"domain": "auth"},
                "options": {"validate": False},
            },
            headers={"Authorization": "Bearer admin-token"},
        )

    # After generation, cache should have at least one entry
    assert cache.size >= 1


def test_cache_invalidated_on_memory_delete() -> None:
    """Memory delete clears the search cache for that tenant/application."""
    cache = TTLCache(ttl_seconds=300)
    cache_key = build_search_cache_key("tenant_cache", "app_cache", "query", {}, 10)
    cache.set(cache_key, "cached_result")

    app = create_app(_settings())
    app.state.cache = cache

    tombstone_filter = TombstoneFilter()
    tombstone_repo = MagicMock()
    tombstone_repo.add = AsyncMock()
    audit_repo = MagicMock()
    audit_repo.record = AsyncMock()

    app.dependency_overrides[get_tombstone_filter] = lambda: tombstone_filter
    app.dependency_overrides[get_tombstone_repo] = lambda: tombstone_repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo

    with TestClient(app) as client:
        resp = client.request(
            "DELETE",
            "/v1/memories/mem_login",
            json={"application_id": "app_cache", "reason": "test"},
            headers={"Authorization": "Bearer admin-token"},
        )

    assert resp.status_code == 200
    # Cache entry should be gone
    assert cache.get(cache_key) is None


def test_cache_invalidation_only_affects_correct_tenant() -> None:
    """Invalidation for tenant_cache:app_cache leaves other tenants' cache intact."""
    cache = TTLCache(ttl_seconds=300)
    key_target = build_search_cache_key("tenant_cache", "app_cache", "q", {}, 10)
    key_other = build_search_cache_key("tenant_other", "app_cache", "q", {}, 10)
    cache.set(key_target, "for_target")
    cache.set(key_other, "for_other")

    app = create_app(_settings())
    app.state.cache = cache

    tombstone_filter = TombstoneFilter()
    tombstone_repo = MagicMock()
    tombstone_repo.add = AsyncMock()
    audit_repo = MagicMock()
    audit_repo.record = AsyncMock()

    app.dependency_overrides[get_tombstone_filter] = lambda: tombstone_filter
    app.dependency_overrides[get_tombstone_repo] = lambda: tombstone_repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo

    with TestClient(app) as client:
        client.request(
            "DELETE",
            "/v1/memories/mem_login",
            json={"application_id": "app_cache"},
            headers={"Authorization": "Bearer admin-token"},
        )

    assert cache.get(key_target) is None
    assert cache.get(key_other) == "for_other"
