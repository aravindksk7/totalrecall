"""Unit tests for StubRagStore and NullRagStore."""

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
