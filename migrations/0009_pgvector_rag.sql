-- Migration 0009: pgvector extension + rag_chunks table + HNSW index

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_chunks (
    id              TEXT        PRIMARY KEY,
    tenant_id       TEXT        NOT NULL DEFAULT '',
    source_ref      TEXT        NOT NULL,
    chunk_index     INTEGER     NOT NULL,
    chunk_text      TEXT        NOT NULL,
    metadata        JSONB       NOT NULL DEFAULT '{}',
    embedding       VECTOR(1536),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, source_ref, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_hnsw
    ON rag_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_tenant_source
    ON rag_chunks (tenant_id, source_ref);
