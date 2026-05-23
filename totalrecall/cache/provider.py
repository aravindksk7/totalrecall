"""In-process TTL cache for memory search results and other expensive lookups.

Entries expire after `ttl_seconds`. Invalidation by prefix allows clearing
all entries for a given tenant/application when memories are deleted or updated.

Thread-safe: a single lock protects the backing store.
"""

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class _Entry:
    value: Any
    expires_at: float


class TTLCache:
    """Simple in-memory TTL cache keyed by arbitrary strings."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        """Return cached value or None if missing or expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.monotonic() > entry.expires_at:
                del self._store[key]
                return None
            return entry.value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = _Entry(value=value, expires_at=time.monotonic() + self._ttl)

    def invalidate_prefix(self, prefix: str) -> int:
        """Remove all entries whose key starts with prefix. Returns count removed."""
        with self._lock:
            to_remove = [k for k in self._store if k.startswith(prefix)]
            for k in to_remove:
                del self._store[k]
            return len(to_remove)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    @property
    def size(self) -> int:
        with self._lock:
            # Evict expired entries while we're counting
            now = time.monotonic()
            expired = [k for k, e in self._store.items() if now > e.expires_at]
            for k in expired:
                del self._store[k]
            return len(self._store)


def build_search_cache_key(tenant_id: str, application_id: str, query: str, filters: dict, limit: int) -> str:
    """Build a stable cache key for a memory search request."""
    payload = json.dumps(
        {"query": query or "", "filters": dict(sorted(filters.items())), "limit": limit},
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"msearch:{tenant_id}:{application_id}:{digest}"


def search_invalidation_prefix(tenant_id: str, application_id: str) -> str:
    """Return the prefix for all memory-search cache keys for a tenant/application."""
    return f"msearch:{tenant_id}:{application_id}:"
