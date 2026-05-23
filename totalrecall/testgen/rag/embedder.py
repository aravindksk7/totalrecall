"""Embedder protocol, OpenAI implementation, and stub."""

import json
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbedderProtocol(Protocol):
    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    """Sync embedder using OpenAI text-embedding-3-small (1536 dims)."""

    _DIMS = 1536
    _MODEL = "text-embedding-3-small"

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com") -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        import httpx

        resp = httpx.post(
            f"{self._base_url}/v1/embeddings",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self._MODEL, "input": texts},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        data.sort(key=lambda d: d["index"])
        return [d["embedding"] for d in data]

    @property
    def dims(self) -> int:
        return self._DIMS


class StubEmbedder:
    """Deterministic zero-vector embedder for tests (no API calls)."""

    _DIMS = 1536

    def embed(self, text: str) -> list[float]:
        return [0.0] * self._DIMS

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self._DIMS for _ in texts]

    @property
    def dims(self) -> int:
        return self._DIMS
