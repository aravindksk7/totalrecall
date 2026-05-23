-- Adapter version mappings: tracks which memory adapter version and external
-- provider_id is active per tenant/application pair.
-- NOTE: provider_mappings already exists in 0001_initial.sql with a different
-- schema (entity-level ID mapping). This table tracks adapter-level config.

CREATE TABLE IF NOT EXISTS adapter_version_mappings (
    id              BIGSERIAL   PRIMARY KEY,
    tenant_id       TEXT        NOT NULL,
    application_id  TEXT        NOT NULL,
    adapter_version TEXT        NOT NULL,
    provider_id     TEXT        NOT NULL,
    metadata        JSONB       NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, application_id, adapter_version)
);

CREATE INDEX IF NOT EXISTS idx_adapter_version_mappings_tenant
    ON adapter_version_mappings (tenant_id, application_id);
