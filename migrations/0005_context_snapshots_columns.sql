-- Ensure context_snapshots has all required columns (fixes stale anonymous volume state).
ALTER TABLE context_snapshots ADD COLUMN IF NOT EXISTS skill_ids JSONB NOT NULL DEFAULT '[]';
ALTER TABLE context_snapshots ADD COLUMN IF NOT EXISTS memory_ids JSONB NOT NULL DEFAULT '[]';
ALTER TABLE context_snapshots ADD COLUMN IF NOT EXISTS estimated_input_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE context_snapshots ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
