-- Skill governance: tracks active/promoted/deprecated status overrides for loaded skills.
-- The file-backed registry provides base status; governance records override at runtime.

CREATE TABLE IF NOT EXISTS skill_governance (
    skill_id        TEXT        NOT NULL,
    version         TEXT        NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'draft',
    promoted_by     TEXT,
    promoted_at     TIMESTAMPTZ,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (skill_id, version)
);

CREATE INDEX IF NOT EXISTS idx_skill_governance_status
    ON skill_governance (status);
