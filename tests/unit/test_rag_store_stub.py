"""Unit tests for StubRagStore, NullRagStore, OpenAIEmbedder, and build_rag_store factory."""

import pytest
import respx
import httpx

from totalrecall.config.feature_flags import ConfigFeatureFlagProvider
from totalrecall.testgen.rag.embedder import OpenAIEmbedder, StubEmbedder
from totalrecall.testgen.rag.factory import build_rag_store
from totalrecall.testgen.rag.models import RagChunk, RagChunkIngestRequest
from totalrecall.testgen.rag.store import NullRagStore, StubRagStore


class TestStubRagStore:
    def _make_chunk(self, i: int) -> RagChunk:
        return RagChunk(chunk_id=f"c{i}", source_ref="doc.md", chunk_text=f"Chunk {i}")

    def test_retrieve_returns_configured_chunks(self):
        chunks = [self._make_chunk(i) for i in range(3)]
        store = StubRagStore(chunks=chunks)
        result = store.retrieve("query", "tenant")
        assert result == chunks

    def test_retrieve_respects_limit(self):
        chunks = [self._make_chunk(i) for i in range(5)]
        store = StubRagStore(chunks=chunks)
        result = store.retrieve("query", "tenant", limit=2)
        assert len(result) == 2

    def test_ingest_returns_count(self):
        store = StubRagStore()
        requests = [
            RagChunkIngestRequest(source_ref="doc.md", chunk_index=i, chunk_text=f"text {i}")
            for i in range(4)
        ]
        assert store.ingest(requests) == 4

    def test_health_returns_ok(self):
        assert StubRagStore().health()["status"] == "ok"

    def test_empty_store_returns_empty_list(self):
        assert StubRagStore().retrieve("q", "t") == []


class TestNullRagStore:
    def test_retrieve_returns_empty(self):
        assert NullRagStore().retrieve("q", "t") == []

    def test_ingest_returns_zero(self):
        store = NullRagStore()
        requests = [RagChunkIngestRequest(source_ref="f.md", chunk_index=0, chunk_text="x")]
        assert store.ingest(requests) == 0

    def test_health_returns_disabled(self):
        assert NullRagStore().health()["status"] == "disabled"


class TestBuildRagStore:
    def _flags(self, overrides: dict):
        return ConfigFeatureFlagProvider(overrides)

    def test_returns_null_when_disabled(self):
        store = build_rag_store(self._flags({"rag.enabled": False}))
        assert isinstance(store, NullRagStore)

    def test_returns_stub_when_adapter_is_stub(self):
        store = build_rag_store(self._flags({"rag.enabled": True, "rag.adapter": "stub"}))
        assert isinstance(store, StubRagStore)

    def test_returns_null_for_unknown_adapter(self):
        store = build_rag_store(self._flags({"rag.enabled": True, "rag.adapter": "nonexistent"}))
        assert isinstance(store, NullRagStore)

    def test_returns_pgvector_store_when_configured(self):
        from totalrecall.testgen.rag.store import PgvectorRagStore

        store = build_rag_store(
            self._flags({"rag.enabled": True, "rag.adapter": "pgvector", "rag.dsn": "postgresql://localhost/test"})
        )
        assert isinstance(store, PgvectorRagStore)

    def test_pgvector_with_credential_provider(self):
        from totalrecall.testgen.rag.store import PgvectorRagStore

        class _Cred:
            def get(self, key: str) -> str:
                return "my-openai-key"

        store = build_rag_store(
            self._flags({"rag.enabled": True, "rag.adapter": "pgvector", "rag.dsn": "postgresql://localhost/test"}),
            credential_provider=_Cred(),
        )
        assert isinstance(store, PgvectorRagStore)

    def test_pgvector_with_failing_credential_provider(self):
        from totalrecall.testgen.rag.store import PgvectorRagStore

        class _FailCred:
            def get(self, key: str) -> str:
                raise RuntimeError("cred not found")

        store = build_rag_store(
            self._flags({"rag.enabled": True, "rag.adapter": "pgvector", "rag.dsn": "postgresql://localhost/test"}),
            credential_provider=_FailCred(),
        )
        assert isinstance(store, PgvectorRagStore)


class TestOpenAIEmbedder:
    def test_instantiation(self):
        embedder = OpenAIEmbedder(api_key="sk-test")
        assert embedder.dims == 1536

    def test_trailing_slash_stripped_from_base_url(self):
        embedder = OpenAIEmbedder(api_key="sk-test", base_url="https://api.openai.com/")
        assert not embedder._base_url.endswith("/")

    @respx.mock
    def test_embed_batch_returns_embeddings(self):
        vectors = [[0.1] * 1536, [0.2] * 1536]
        mock_response = {
            "data": [
                {"index": 0, "embedding": vectors[0]},
                {"index": 1, "embedding": vectors[1]},
            ]
        }
        respx.post("https://api.openai.com/v1/embeddings").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        embedder = OpenAIEmbedder(api_key="sk-test")
        result = embedder.embed_batch(["hello", "world"])
        assert len(result) == 2
        assert result[0] == vectors[0]
        assert result[1] == vectors[1]

    @respx.mock
    def test_embed_delegates_to_embed_batch(self):
        vector = [0.5] * 1536
        mock_response = {"data": [{"index": 0, "embedding": vector}]}
        respx.post("https://api.openai.com/v1/embeddings").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        embedder = OpenAIEmbedder(api_key="sk-test")
        result = embedder.embed("hello")
        assert result == vector


class TestStubEmbedder:
    def test_embed_returns_zero_vector(self):
        embedder = StubEmbedder()
        result = embedder.embed("hello")
        assert len(result) == 1536
        assert all(v == 0.0 for v in result)

    def test_embed_batch_returns_multiple_vectors(self):
        embedder = StubEmbedder()
        result = embedder.embed_batch(["a", "b", "c"])
        assert len(result) == 3

    def test_dims_is_1536(self):
        assert StubEmbedder().dims == 1536


# --- PgvectorRagStore tests (psycopg2 mocked) ---


class TestPgvectorRagStore:
    def _make_store(self):
        from totalrecall.testgen.rag.store import PgvectorRagStore

        return PgvectorRagStore(dsn="postgresql://localhost/test", embedder=StubEmbedder())

    def test_instantiation(self):
        store = self._make_store()
        assert store._dsn == "postgresql://localhost/test"

    def test_retrieve_returns_chunks(self):
        from unittest.mock import MagicMock, patch
        from totalrecall.testgen.rag.store import PgvectorRagStore

        chunk_id = "abc-123"
        mock_row = (chunk_id, "doc.md", "chunk text", {"key": "val"}, 0.9)
        mock_cur = MagicMock()
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.return_value = [mock_row]

        mock_conn = MagicMock()
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cur

        store = self._make_store()
        with patch.object(store, "_connect", return_value=mock_conn):
            results = store.retrieve("query text", "tenant1", limit=1)

        assert len(results) == 1
        assert results[0].chunk_id == chunk_id
        assert results[0].source_ref == "doc.md"
        assert results[0].similarity == 0.9

    def test_ingest_inserts_chunks(self):
        from unittest.mock import MagicMock, patch
        from totalrecall.testgen.rag.models import RagChunkIngestRequest
        from totalrecall.testgen.rag.store import PgvectorRagStore

        mock_cur = MagicMock()
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cur

        store = self._make_store()
        chunks = [
            RagChunkIngestRequest(tenant_id="t1", source_ref="doc.md", chunk_index=0, chunk_text="hello world"),
            RagChunkIngestRequest(tenant_id="t1", source_ref="doc.md", chunk_index=1, chunk_text="foo bar"),
        ]
        with patch.object(store, "_connect", return_value=mock_conn):
            count = store.ingest(chunks)

        assert count == 2
        mock_cur.executemany.assert_called_once()

    def test_ingest_empty_returns_zero(self):
        store = self._make_store()
        assert store.ingest([]) == 0

    def test_health_returns_ok_when_connect_succeeds(self):
        from unittest.mock import MagicMock, patch

        mock_cur = MagicMock()
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cur

        store = self._make_store()
        with patch.object(store, "_connect", return_value=mock_conn):
            result = store.health()

        assert result["status"] == "ok"

    def test_health_returns_error_when_connect_fails(self):
        from unittest.mock import patch

        store = self._make_store()
        with patch.object(store, "_connect", side_effect=Exception("connection refused")):
            result = store.health()

        assert result["status"] == "error"
        assert "connection refused" in result["detail"]
