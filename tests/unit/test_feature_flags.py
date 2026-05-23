from typing import Self
from urllib.request import Request

from totalrecall.config.feature_flags import (
    ConfigFeatureFlagProvider,
    ExternalFeatureFlagProvider,
)


class _Response:
    def __init__(self, body: str) -> None:
        self._body = body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body.encode("utf-8")


def test_feature_flags_resolve_bool_and_string_values() -> None:
    provider = ConfigFeatureFlagProvider(
        {
            "memory.adapter": "stub",
            "memory.write_enabled": "true",
        }
    )

    assert provider.get_string("memory.adapter") == "stub"
    assert provider.get_bool("memory.write_enabled") is True
    assert provider.get_bool("missing") is False


def test_feature_flag_snapshot_returns_copy() -> None:
    provider = ConfigFeatureFlagProvider({"a": "b"})

    snapshot = provider.snapshot()

    assert snapshot.values == {"a": "b"}


def test_external_feature_flags_read_values_object() -> None:
    calls: list[Request] = []

    def opener(request: Request, timeout: int) -> _Response:
        calls.append(request)
        assert timeout == 6
        return _Response('{"values": {"memory.adapter": "mem0_v1", "enabled": true}}')

    provider = ExternalFeatureFlagProvider(
        "https://flags.example.test/openfeature",
        fallback=ConfigFeatureFlagProvider({"memory.adapter": "stub"}),
        auth_token="flag-token",
        timeout_seconds=6,
        cache_ttl_seconds=30,
        opener=opener,
        clock=lambda: 100.0,
    )

    assert provider.get_string("memory.adapter") == "mem0_v1"
    assert provider.get_bool("enabled") is True
    assert calls[0].get_header("Authorization") == "Bearer flag-token"


def test_external_feature_flags_cache_snapshot() -> None:
    count = 0

    def opener(request: Request, timeout: int) -> _Response:
        nonlocal count
        count += 1
        return _Response('{"memory.adapter": "stub"}')

    provider = ExternalFeatureFlagProvider(
        "https://flags.example.test/openfeature",
        fallback=ConfigFeatureFlagProvider({}),
        opener=opener,
        clock=lambda: 10.0,
    )

    assert provider.get_string("memory.adapter") == "stub"
    assert provider.get_string("memory.adapter") == "stub"
    assert count == 1


def test_external_feature_flags_fall_back_on_fetch_error() -> None:
    def opener(request: Request, timeout: int) -> _Response:
        raise OSError("network down")

    provider = ExternalFeatureFlagProvider(
        "https://flags.example.test/openfeature",
        fallback=ConfigFeatureFlagProvider({"memory.adapter": "stub"}),
        opener=opener,
    )

    assert provider.get_string("memory.adapter") == "stub"
    assert provider.last_error is not None
