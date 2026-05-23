create table if not exists learning_discoveries (
    id              text primary key,
    run_id          text not null references learning_runs(id),
    tenant_id       text not null,
    application_id  text not null,
    discovery_type  text not null,
    status          text not null default 'discovered',
    delta_state     text not null,
    summary         text not null,
    confidence      float not null default 1.0,
    source          jsonb not null default '{}'::jsonb,
    proposed_tags   jsonb not null default '{}'::jsonb,
    content_hash    text,
    warnings        jsonb not null default '[]'::jsonb,
    approved_by     text,
    approved_at     timestamptz,
    rejection_reason text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index if not exists idx_learning_discoveries_run
    on learning_discoveries (run_id);

create index if not exists idx_learning_discoveries_tenant_status
    on learning_discoveries (tenant_id, status);

create index if not exists idx_learning_runs_tenant
    on learning_runs (tenant_id, application_id);
