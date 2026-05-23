-- Drop stale payload column from context_snapshots (left over from an earlier schema iteration).
ALTER TABLE context_snapshots DROP COLUMN IF EXISTS payload;
