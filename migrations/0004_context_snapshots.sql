-- Context snapshot: reproducible record of which skills and memories were used per generation
CREATE TABLE IF NOT EXISTS context_snapshots (
    id TEXT NOT NULL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    application_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    skill_ids JSONB NOT NULL DEFAULT '[]',
    memory_ids JSONB NOT NULL DEFAULT '[]',
    estimated_input_tokens INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS context_snapshots_tenant_app_idx
    ON context_snapshots (tenant_id, application_id);

CREATE INDEX IF NOT EXISTS context_snapshots_request_id_idx
    ON context_snapshots (request_id);
