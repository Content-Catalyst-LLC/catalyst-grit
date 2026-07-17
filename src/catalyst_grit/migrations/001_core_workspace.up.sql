CREATE TABLE projects (
    project_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived','deleted')),
    visibility TEXT NOT NULL DEFAULT 'private' CHECK (visibility = 'private'),
    owner_id TEXT NOT NULL,
    retention_days INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    deleted_at TEXT
);

CREATE TABLE recovery_records (
    record_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    current_revision_id TEXT,
    status TEXT NOT NULL,
    visibility TEXT NOT NULL DEFAULT 'private' CHECK (visibility = 'private'),
    retention_until TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    deleted_at TEXT
);

CREATE TABLE record_revisions (
    revision_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES recovery_records(record_id) ON DELETE CASCADE,
    revision_number INTEGER NOT NULL,
    canonical_json TEXT NOT NULL,
    request_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    UNIQUE(record_id, revision_number),
    UNIQUE(record_id, content_sha256)
);

CREATE INDEX record_revisions_record_idx ON record_revisions(record_id, revision_number DESC);
CREATE INDEX recovery_records_project_idx ON recovery_records(project_id, updated_at DESC);

CREATE TABLE status_history (
    history_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX status_history_entity_idx ON status_history(entity_type, entity_id, created_at);
