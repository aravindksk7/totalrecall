"""Unit tests for RAG text chunking logic."""

from totalrecall.testgen.rag.ingest import RagIngestRunner, _chunk_text
from totalrecall.testgen.rag.store import StubRagStore


class TestChunkText:
    def test_empty_text_returns_empty(self):
        assert _chunk_text("") == []

    def test_single_chunk_when_text_fits(self):
        text = " ".join(["word"] * 100)
        chunks = _chunk_text(text, chunk_size=512, overlap=64)
        assert len(chunks) == 1

    def test_multiple_chunks_when_text_exceeds_size(self):
        text = " ".join([f"w{i}" for i in range(1000)])
        chunks = _chunk_text(text, chunk_size=512, overlap=64)
        assert len(chunks) > 1

    def test_overlap_means_chunks_share_words(self):
        words = [f"w{i}" for i in range(600)]
        text = " ".join(words)
        chunks = _chunk_text(text, chunk_size=512, overlap=64)
        last_words_of_first = set(chunks[0].split()[-64:])
        first_words_of_second = set(chunks[1].split()[:64])
        assert last_words_of_first & first_words_of_second  # overlap exists

    def test_no_empty_chunks_produced(self):
        text = " ".join([f"x{i}" for i in range(2000)])
        chunks = _chunk_text(text, chunk_size=200, overlap=50)
        assert all(c.strip() for c in chunks)

    def test_chunk_size_respected(self):
        text = " ".join([f"t{i}" for i in range(1000)])
        chunks = _chunk_text(text, chunk_size=100, overlap=10)
        for chunk in chunks:
            assert len(chunk.split()) <= 100


class TestRagIngestRunner:
    def test_ingest_file_calls_store(self, tmp_path):
        doc = tmp_path / "guide.md"
        doc.write_text(" ".join(["word"] * 100), encoding="utf-8")
        store = StubRagStore()
        runner = RagIngestRunner(store, tenant_id="t1")
        count = runner.ingest_file(doc)
        assert count == 1  # StubRagStore.ingest returns len(chunks)

    def test_ingest_file_uses_filename_as_source_ref(self, tmp_path):
        doc = tmp_path / "testing_guide.md"
        doc.write_text("Some text content here", encoding="utf-8")

        ingested: list = []

        class CapturingStore:
            def ingest(self, chunks):
                ingested.extend(chunks)
                return len(chunks)

        runner = RagIngestRunner(CapturingStore(), tenant_id="")
        runner.ingest_file(doc)
        assert all(c.source_ref == "testing_guide.md" for c in ingested)
