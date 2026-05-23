create table if not exists catalogue_entries (
    id text primary key,
    tenant_id text not null,
    application_id text not null,
    category text not null,
    status text not null,
    summary text not null,
    source jsonb not null default '{}'::jsonb,
    tags jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_catalogue_entries_tenant_status
    on catalogue_entries (tenant_id, status);

create table if not exists memory_tombstones (
    memory_id text primary key,
    tenant_id text not null,
    application_id text not null,
    reason text,
    deleted_by text not null,
    deleted_at timestamptz not null default now()
);

create table if not exists provider_mappings (
    id text primary key,
    tenant_id text not null,
    provider text not null,
    provider_entity_id text not null,
    adapter_version text not null,
    totalrecall_entity_id text not null,
    created_at timestamptz not null default now(),
    unique (tenant_id, provider, provider_entity_id)
);

create table if not exists context_snapshots (
    id text primary key,
    tenant_id text not null,
    application_id text not null,
    request_id text not null,
    payload jsonb not null,
    created_at timestamptz not null default now()
);

create table if not exists audit_events (
    id text primary key,
    tenant_id text not null,
    actor_id text not null,
    event_type text not null,
    subject_type text not null,
    subject_id text,
    details jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_audit_events_tenant_created
    on audit_events (tenant_id, created_at desc);

create table if not exists feature_flag_snapshots (
    id text primary key,
    tenant_id text not null,
    request_id text,
    flags jsonb not null,
    created_at timestamptz not null default now()
);

create table if not exists learning_runs (
    id text primary key,
    tenant_id text not null,
    application_id text not null,
    scope jsonb not null,
    trigger_type text not null,
    status text not null,
    summary jsonb not null default '{}'::jsonb,
    started_at timestamptz not null default now(),
    completed_at timestamptz
);

create table if not exists skill_versions (
    id text primary key,
    tenant_id text not null,
    skill_id text not null,
    version text not null,
    status text not null,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (tenant_id, skill_id, version)
);
