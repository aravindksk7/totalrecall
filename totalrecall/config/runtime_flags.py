import json
from pathlib import Path
from typing import Any

from totalrecall.config.feature_flags import FeatureFlagProvider, FeatureFlagSnapshot


class RuntimeFeatureFlagStore:
    _FILENAME = "runtime_feature_flags.json"

    def __init__(self, local_secrets_dir: Path) -> None:
        self._path = local_secrets_dir / self._FILENAME

    def values(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        values = payload.get("values") if isinstance(payload, dict) else None
        return dict(values) if isinstance(values, dict) else {}

    def set(self, key: str, value: Any) -> None:
        values = self.values()
        values[key] = value
        self._write(values)

    def delete(self, key: str) -> None:
        values = self.values()
        values.pop(key, None)
        self._write(values)

    def _write(self, values: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"values": values}, indent=2, sort_keys=True),
            encoding="utf-8",
        )


class RuntimeFeatureFlagProvider:
    """Feature flag provider with local runtime overrides layered on top."""

    def __init__(
        self,
        fallback: FeatureFlagProvider,
        runtime_store: RuntimeFeatureFlagStore,
    ) -> None:
        self._fallback = fallback
        self._runtime_store = runtime_store

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
        values = self._fallback.snapshot().values
        values.update(self._runtime_store.values())
        return FeatureFlagSnapshot(values=values)
