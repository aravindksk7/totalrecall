alter table catalogue_entries
    add column if not exists application_id text not null default '',
    add column if not exists owner text,
    add column if not exists approved_by text,
    add column if not exists approved_at timestamptz,
    add column if not exists deleted_by text,
    add column if not exists deleted_at timestamptz;
