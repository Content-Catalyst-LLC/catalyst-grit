CREATE TABLE connected_workflows (
    workflow_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    record_id TEXT NOT NULL REFERENCES recovery_records(record_id) ON DELETE CASCADE,
    contract_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('planned','active','needs_review','blocked','completed','archived')),
    current_step_key TEXT NOT NULL,
    started_by TEXT NOT NULL,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(project_id, record_id, contract_version)
);
CREATE INDEX connected_workflows_project_idx ON connected_workflows(project_id, status, updated_at);

CREATE TABLE connected_workflow_steps (
    step_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES connected_workflows(workflow_id) ON DELETE CASCADE,
    step_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','ready','in_progress','needs_review','blocked','completed','skipped')),
    source_type TEXT NOT NULL DEFAULT '',
    source_id TEXT NOT NULL DEFAULT '',
    source_hash TEXT NOT NULL DEFAULT '',
    output_json TEXT NOT NULL DEFAULT '{}',
    human_review_required INTEGER NOT NULL DEFAULT 0 CHECK (human_review_required IN (0,1)),
    reviewed_by TEXT,
    reviewed_at TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(workflow_id, step_key),
    UNIQUE(workflow_id, ordinal)
);
CREATE INDEX connected_workflow_steps_idx ON connected_workflow_steps(workflow_id, ordinal);

CREATE TABLE connected_workflow_events (
    workflow_event_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES connected_workflows(workflow_id) ON DELETE CASCADE,
    step_key TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL CHECK (event_type IN ('created','refreshed','step_changed','reviewed','completed','blocked','archived')),
    from_status TEXT,
    to_status TEXT,
    actor_id TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX connected_workflow_events_idx ON connected_workflow_events(workflow_id, created_at);

CREATE TABLE artifact_connections (
    connection_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    source_product TEXT NOT NULL,
    source_artifact_type TEXT NOT NULL,
    source_artifact_id TEXT NOT NULL,
    source_version TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    target_product TEXT NOT NULL,
    target_artifact_type TEXT NOT NULL,
    target_artifact_id TEXT NOT NULL,
    target_version TEXT NOT NULL,
    target_hash TEXT NOT NULL,
    relation TEXT NOT NULL CHECK (relation IN ('informs','supports','challenges','derived_from','supersedes','monitors','publishes','hands_off_to')),
    validation_state TEXT NOT NULL CHECK (validation_state IN ('valid','stale','conflict','invalid')),
    provenance_json TEXT NOT NULL DEFAULT '[]',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_checked_at TEXT NOT NULL,
    UNIQUE(project_id, source_product, source_artifact_id, target_product, target_artifact_id, relation)
);
CREATE INDEX artifact_connections_project_idx ON artifact_connections(project_id, validation_state, created_at);

CREATE TABLE artifact_connection_events (
    connection_event_id TEXT PRIMARY KEY,
    connection_id TEXT NOT NULL REFERENCES artifact_connections(connection_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('created','validated','marked_stale','conflict_recorded','invalidated')),
    from_state TEXT,
    to_state TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX artifact_connection_events_idx ON artifact_connection_events(connection_id, created_at);

CREATE TABLE portable_platform_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    record_id TEXT REFERENCES recovery_records(record_id) ON DELETE SET NULL,
    format TEXT NOT NULL,
    bundle_hash TEXT NOT NULL,
    bundle_json TEXT NOT NULL,
    verification_state TEXT NOT NULL CHECK (verification_state IN ('verified','invalid')),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    verified_at TEXT NOT NULL
);
CREATE INDEX portable_platform_snapshots_project_idx ON portable_platform_snapshots(project_id, created_at);

CREATE TABLE platform_sync_events (
    sync_event_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    connector TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('inbound','outbound','bidirectional')),
    status TEXT NOT NULL CHECK (status IN ('planned','completed','partial','failed','conflict')),
    source_cursor TEXT NOT NULL DEFAULT '',
    target_cursor TEXT NOT NULL DEFAULT '',
    artifact_count INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT NOT NULL DEFAULT '{}',
    actor_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX platform_sync_events_project_idx ON platform_sync_events(project_id, connector, created_at);

CREATE TRIGGER connected_workflow_events_no_update BEFORE UPDATE ON connected_workflow_events BEGIN SELECT RAISE(ABORT, 'connected workflow events are append-only'); END;
CREATE TRIGGER connected_workflow_events_guard_delete BEFORE DELETE ON connected_workflow_events WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'connected workflow events are append-only'); END;
CREATE TRIGGER artifact_connection_events_no_update BEFORE UPDATE ON artifact_connection_events BEGIN SELECT RAISE(ABORT, 'artifact connection events are append-only'); END;
CREATE TRIGGER artifact_connection_events_guard_delete BEFORE DELETE ON artifact_connection_events WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'artifact connection events are append-only'); END;
CREATE TRIGGER portable_platform_snapshots_no_update BEFORE UPDATE ON portable_platform_snapshots BEGIN SELECT RAISE(ABORT, 'portable platform snapshots are append-only'); END;
CREATE TRIGGER portable_platform_snapshots_guard_delete BEFORE DELETE ON portable_platform_snapshots WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'portable platform snapshots are append-only'); END;
CREATE TRIGGER platform_sync_events_no_update BEFORE UPDATE ON platform_sync_events BEGIN SELECT RAISE(ABORT, 'platform sync events are append-only'); END;
CREATE TRIGGER platform_sync_events_guard_delete BEFORE DELETE ON platform_sync_events WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'platform sync events are append-only'); END;
