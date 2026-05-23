import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel


class FeatureFlagSnapshot(BaseModel):
    values: dict[str, Any]


class ConfigFeatureFlagProvider:
    def __init__(self, flags: dict[str, Any]) -> None:
        self._flags = dict(flags)

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self._flags.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def get_string(self, key: str, default: str = "") -> str:
        value = self._flags.get(key, default)
        return str(value)

    def snapshot(self) -> FeatureFlagSnapshot:
        return FeatureFlagSnapshot(values=dict(self._flags))


class FeatureFlagProvider(Protocol):
    def get_bool(self, key: str, default: bool = False) -> bool:
        """Resolve a feature flag as a boolean."""

    def get_string(self, key: str, default: str = "") -> str:
        """Resolve a feature flag as a string."""

    def snapshot(self) -> FeatureFlagSnapshot:
        """Return a copy of all currently resolved flag values."""


class ExternalFeatureFlagProvider:
    """OpenFeature-compatible HTTP adapter with config-backed fallback.

    The external endpoint can return either {"values": {...}} or a raw object
    containing flag keys. Values are cached for a short TTL to avoid making
    every request depend on the flag service.
    """

    def __init__(
        self,
        url: str,
        *,
        fallback: FeatureFlagProvider,
        auth_token: str | None = None,
        timeout_seconds: int = 5,
        cache_ttl_seconds: int = 30,
        opener=urllib.request.urlopen,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not url:
            raise ValueError("External feature flag URL must not be empty")
        if timeout_seconds < 1:
            raise ValueError("External feature flag timeout must be >= 1 second")
        if cache_ttl_seconds < 0:
            raise ValueError("External feature flag cache TTL must be >= 0 seconds")
        self._url = url
        self._fallback = fallback
        self._auth_token = auth_token
        self._timeout_seconds = timeout_seconds
        self._cache_ttl_seconds = cache_ttl_seconds
        self._opener = opener
        self._clock = clock
        self._cache: FeatureFlagSnapshot | None = None
        self._cache_expires_at = 0.0
        self.last_error: str | None = None

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self.snapshot().values.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def get_string(self, key: str, default: str = "") -> str:
        value = self.snapshot().values.get(key, default)
        return str(value)

    def snapshot(self) -> FeatureFlagSnapshot:
        now = self._clock()
        if self._cache is not None and now < self._cache_expires_at:
            return FeatureFlagSnapshot(values=dict(self._cache.values))

        try:
            snapshot = self._fetch()
        except Exception as exc:
            self.last_error = str(exc)
            return self._fallback.snapshot()

        self._cache = snapshot
        self._cache_expires_at = now + self._cache_ttl_seconds
        self.last_error = None
        return FeatureFlagSnapshot(values=dict(snapshot.values))

    def _fetch(self) -> FeatureFlagSnapshot:
        request = urllib.request.Request(self._url)
        if self._auth_token:
            request.add_header("Authorization", f"Bearer {self._auth_token}")

        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except (OSError, urllib.error.URLError) as exc:
            raise RuntimeError("External feature flag service is unavailable") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("External feature flag response is not valid JSON") from exc

        values = payload.get("values") if isinstance(payload, dict) else None
        if values is None and isinstance(payload, dict):
            values = payload
        if not isinstance(values, dict):
            raise RuntimeError("External feature flag response must be an object")
        return FeatureFlagSnapshot(values=dict(values))
