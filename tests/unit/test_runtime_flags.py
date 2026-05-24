"""Unit tests for RuntimeFeatureFlagStore and RuntimeFeatureFlagProvider."""

import json
from pathlib import Path

import pytest

from totalrecall.config.feature_flags import ConfigFeatureFlagProvider
from totalrecall.config.runtime_flags import RuntimeFeatureFlagProvider, RuntimeFeatureFlagStore


def _store(tmp_path: Path) -> RuntimeFeatureFlagStore:
    return RuntimeFeatureFlagStore(tmp_path / "local-secrets")


def test_runtime_flag_store_returns_empty_when_file_missing(tmp_path) -> None:
    store = _store(tmp_path)
    assert store.values() == {}


def test_runtime_flag_store_returns_empty_on_invalid_json(tmp_path) -> None:
    secrets = tmp_path / "local-secrets"
    secrets.mkdir()
    (secrets / "runtime_feature_flags.json").write_text("not-json{{{", encoding="utf-8")

    store = _store(tmp_path)
    assert store.values() == {}


def test_runtime_flag_store_set_creates_file(tmp_path) -> None:
    store = _store(tmp_path)
    store.set("memory.adapter", "mem0_v1")

    values = store.values()
    assert values["memory.adapter"] == "mem0_v1"


def test_runtime_flag_store_delete_removes_key(tmp_path) -> None:
    store = _store(tmp_path)
    store.set("memory.adapter", "mem0_v1")
    store.set("memory.write_enabled", True)
    store.delete("memory.adapter")

    values = store.values()
    assert "memory.adapter" not in values
    assert values["memory.write_enabled"] is True


def test_runtime_flag_store_delete_noop_when_key_missing(tmp_path) -> None:
    store = _store(tmp_path)
    store.delete("nonexistent")
    assert store.values() == {}


def test_runtime_flag_provider_overrides_fallback(tmp_path) -> None:
    store = _store(tmp_path)
    store.set("memory.adapter", "mem0_v1")
    fallback = ConfigFeatureFlagProvider({"memory.adapter": "stub", "other.flag": "yes"})
    provider = RuntimeFeatureFlagProvider(fallback, store)

    assert provider.get_string("memory.adapter") == "mem0_v1"
    assert provider.get_string("other.flag") == "yes"


def test_runtime_flag_provider_returns_fallback_when_no_override(tmp_path) -> None:
    store = _store(tmp_path)
    fallback = ConfigFeatureFlagProvider({"memory.adapter": "stub"})
    provider = RuntimeFeatureFlagProvider(fallback, store)

    assert provider.get_string("memory.adapter") == "stub"


def test_runtime_flag_provider_get_bool_true(tmp_path) -> None:
    store = _store(tmp_path)
    store.set("memory.write_enabled", True)
    provider = RuntimeFeatureFlagProvider(ConfigFeatureFlagProvider({}), store)

    assert provider.get_bool("memory.write_enabled") is True


def test_runtime_flag_provider_get_bool_string_true(tmp_path) -> None:
    store = _store(tmp_path)
    store.set("flag", "true")
    provider = RuntimeFeatureFlagProvider(ConfigFeatureFlagProvider({}), store)

    assert provider.get_bool("flag") is True


def test_runtime_flag_provider_get_bool_numeric(tmp_path) -> None:
    store = _store(tmp_path)
    store.set("flag", 1)
    provider = RuntimeFeatureFlagProvider(ConfigFeatureFlagProvider({}), store)

    assert provider.get_bool("flag") is True


def test_runtime_flag_provider_snapshot_merges_runtime_over_base(tmp_path) -> None:
    store = _store(tmp_path)
    store.set("memory.adapter", "mem0_v1")
    fallback = ConfigFeatureFlagProvider({"memory.adapter": "stub", "jira.enabled": False})
    provider = RuntimeFeatureFlagProvider(fallback, store)

    snap = provider.snapshot()
    assert snap.values["memory.adapter"] == "mem0_v1"
    assert snap.values["jira.enabled"] is False
