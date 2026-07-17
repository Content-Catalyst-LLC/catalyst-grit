CREATE TABLE institutional_policies (
    policy_id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE,
    policy_type TEXT NOT NULL CHECK (policy_type IN ('retention','export_redaction','access_review','methodology_governance','schema_deprecation')),
    version INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft','active','retired')),
    config_json TEXT NOT NULL DEFAULT '{}',
    effective_at TEXT NOT NULL,
    expires_at TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, policy_type, version)
);
CREATE INDEX institutional_policies_lookup_idx ON institutional_policies(project_id, policy_type, status, version);

CREATE TABLE access_reviews (
    access_review_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    subject_type TEXT NOT NULL CHECK (subject_type IN ('member','api_client','publication','project')),
    subject_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approved','changes_required','revoked','expired')),
    reviewer_id TEXT NOT NULL,
    scope_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT NOT NULL,
    next_review_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX access_reviews_project_idx ON access_reviews(project_id, subject_type, subject_id, created_at);

CREATE TABLE api_clients (
    client_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    scopes_json TEXT NOT NULL DEFAULT '[]',
    project_ids_json TEXT NOT NULL DEFAULT '[]',
    rate_limit_per_minute INTEGER NOT NULL DEFAULT 60 CHECK (rate_limit_per_minute BETWEEN 1 AND 10000),
    status TEXT NOT NULL CHECK (status IN ('active','revoked')),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE TABLE api_rate_windows (
    client_id TEXT NOT NULL REFERENCES api_clients(client_id) ON DELETE CASCADE,
    window_start TEXT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (client_id, window_start)
);

CREATE TABLE api_audit_events (
    api_event_id TEXT PRIMARY KEY,
    client_id TEXT REFERENCES api_clients(client_id) ON DELETE SET NULL,
    actor_id TEXT NOT NULL,
    method TEXT NOT NULL,
    route TEXT NOT NULL,
    project_id TEXT,
    response_status INTEGER NOT NULL,
    request_hash TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX api_audit_events_client_idx ON api_audit_events(client_id, created_at);

CREATE TABLE publication_artifacts (
    publication_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    record_id TEXT REFERENCES recovery_records(record_id) ON DELETE SET NULL,
    report_type TEXT NOT NULL CHECK (report_type IN ('recovery_brief','facilitated_review_brief','action_plan','learning_loop_report','adaptation_proposal','monitoring_summary','decision_studio_handoff')),
    format TEXT NOT NULL CHECK (format IN ('json','jsonld','markdown','html','csv','pdf_request','bundle')),
    visibility TEXT NOT NULL CHECK (visibility IN ('private','internal','public')),
    redaction_policy TEXT NOT NULL CHECK (redaction_policy IN ('none','internal','public')),
    content_hash TEXT NOT NULL,
    content_text TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX publication_artifacts_project_idx ON publication_artifacts(project_id, report_type, created_at);

CREATE TABLE publication_events (
    publication_event_id TEXT PRIMARY KEY,
    publication_id TEXT NOT NULL REFERENCES publication_artifacts(publication_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('created','reviewed','approved','published','withdrawn','exported')),
    actor_id TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX publication_events_idx ON publication_events(publication_id, created_at);

CREATE TABLE methodology_registry (
    methodology_id TEXT PRIMARY KEY,
    profile_name TEXT NOT NULL,
    profile_version TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft','approved','deprecated')),
    approved_by TEXT,
    effective_at TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(profile_name, profile_version)
);

CREATE TABLE schema_deprecations (
    deprecation_id TEXT PRIMARY KEY,
    schema_name TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    replacement_version TEXT,
    status TEXT NOT NULL CHECK (status IN ('announced','deprecated','retired')),
    announced_at TEXT NOT NULL,
    sunset_at TEXT,
    migration_notes TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(schema_name, schema_version)
);

CREATE TRIGGER access_reviews_no_update BEFORE UPDATE ON access_reviews BEGIN SELECT RAISE(ABORT, 'access reviews are append-only'); END;
CREATE TRIGGER access_reviews_guard_delete BEFORE DELETE ON access_reviews WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'access reviews are append-only'); END;
CREATE TRIGGER api_audit_events_no_update BEFORE UPDATE ON api_audit_events BEGIN SELECT RAISE(ABORT, 'API audit events are append-only'); END;
CREATE TRIGGER api_audit_events_guard_delete BEFORE DELETE ON api_audit_events WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'API audit events are append-only'); END;
CREATE TRIGGER publication_events_no_update BEFORE UPDATE ON publication_events BEGIN SELECT RAISE(ABORT, 'publication events are append-only'); END;
CREATE TRIGGER publication_events_guard_delete BEFORE DELETE ON publication_events WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'publication events are append-only'); END;
