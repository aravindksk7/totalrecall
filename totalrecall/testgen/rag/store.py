"""RAG store protocol, pgvector implementation, stub, and null."""

import uuid
from typing import Protocol, runtime_checkable

from totalrecall.testgen.rag.models import RagChunk, RagChunkIngestRequest


@runtime_checkable
class RagStoreProtocol(Protocol):
    def retrieve(self, query: str, tenant_id: str, limit: int = 5) -> list[RagChunk]: ...
    def ingest(self, chunks: list[RagChunkIngestRequest]) -> int: ...
    def health(self) -> dict: ...


class PgvectorRagStore:
    """Sync psycopg2 store backed by pgvector HNSW index."""

    def __init__(self, dsn: str, embedder) -> None:
        self._dsn = dsn
        self._embedder = embedder

    def _connect(self):
        import psycopg2
        return psycopg2.connect(self._dsn)

    def retrieve(self, query: str, tenant_id: str, limit: int = 5) -> list[RagChunk]:
        embedding = self._embedder.embed(query)
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
        sql = """
            SELECT id, source_ref, chunk_text, metadata,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM rag_chunks
            WHERE tenant_id = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (vec_str, tenant_id, vec_str, limit))
                rows = cur.fetchall()
        return [
            RagChunk(
                chunk_id=row[0],
                source_ref=row[1],
                chunk_text=row[2],
                metadata=row[3] or {},
                similarity=float(row[4]),
            )
            for row in rows
        ]

    def ingest(self, chunks: list[RagChunkIngestRequest]) -> int:
        if not chunks:
            return 0
        texts = [c.chunk_text for c in chunks]
        embeddings = self._embedder.embed_batch(texts)
        sql = """
            INSERT INTO rag_chunks (id, tenant_id, source_ref, chunk_index, chunk_text, metadata, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
            ON CONFLICT (tenant_id, source_ref, chunk_index) DO UPDATE
                SET chunk_text = EXCLUDED.chunk_text,
                    metadata   = EXCLUDED.metadata,
                    embedding  = EXCLUDED.embedding,
                    updated_at = NOW()
        """
        import json
        rows = [
            (
                str(uuid.uuid4()),
                c.tenant_id,
                c.source_ref,
                c.chunk_index,
                c.chunk_text,
                json.dumps(c.metadata),
                "[" + ",".join(str(x) for x in emb) + "]",
            )
            for c, emb in zip(chunks, embeddings)
        ]
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
            conn.commit()
        return len(rows)

    def health(self) -> dict:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            return {"status": "ok"}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}


class StubRagStore:
    """Returns a configurable list of chunks; no database access."""

    def __init__(self, chunks: list[RagChunk] | None = None) -> None:
        self._chunks = chunks or []

    def retrieve(self, query: str, tenant_id: str, limit: int = 5) -> list[RagChunk]:
        return self._chunks[:limit]

    def ingest(self, chunks: list[RagChunkIngestRequest]) -> int:
        return len(chunks)

    def health(self) -> dict:
        return {"status": "ok", "adapter": "stub"}


class NullRagStore:
    """Always returns empty results; used when rag.enabled=False."""

    def retrieve(self, query: str, tenant_id: str, limit: int = 5) -> list[RagChunk]:
        return []

    def ingest(self, chunks: list[RagChunkIngestRequest]) -> int:
        return 0

    def health(self) -> dict:
        return {"status": "disabled"}
