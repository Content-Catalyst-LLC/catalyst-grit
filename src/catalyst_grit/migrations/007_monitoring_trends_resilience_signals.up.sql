CREATE TABLE monitoring_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    record_id TEXT NOT NULL REFERENCES recovery_records(record_id) ON DELETE CASCADE,
    revision_id TEXT NOT NULL REFERENCES record_revisions(revision_id) ON DELETE CASCADE,
    revision_number INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    methodology_profile_version TEXT NOT NULL,
    recovery_score REAL NOT NULL,
    component_scores_json TEXT NOT NULL,
    condition_metrics_json TEXT NOT NULL,
    completeness_percent REAL NOT NULL,
    confidence_level TEXT NOT NULL,
    confidence_score REAL NOT NULL,
    action_counts_json TEXT NOT NULL,
    blocker_counts_json TEXT NOT NULL,
    checkpoint_counts_json TEXT NOT NULL,
    reopened_count INTEGER NOT NULL DEFAULT 0,
    pattern_keys_json TEXT NOT NULL DEFAULT '[]',
    system_change_counts_json TEXT NOT NULL DEFAULT '{}',
    stable_threshold REAL NOT NULL,
    source_record_hash TEXT NOT NULL,
    source_revision_hash TEXT NOT NULL,
    source_trace_json TEXT NOT NULL DEFAULT '{}',
    note TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX monitoring_snapshots_record_idx ON monitoring_snapshots(record_id, observed_at, created_at);
CREATE INDEX monitoring_snapshots_project_idx ON monitoring_snapshots(project_id, observed_at, created_at);

CREATE TABLE monitoring_snapshot_events (
    event_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES monitoring_snapshots(snapshot_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('captured','annotated','reviewed')),
    signal_key TEXT NOT NULL DEFAULT '',
    actor_id TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX monitoring_snapshot_events_idx ON monitoring_snapshot_events(snapshot_id, created_at);

CREATE TABLE monitoring_reviews (
    review_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    record_id TEXT REFERENCES recovery_records(record_id) ON DELETE CASCADE,
    scope TEXT NOT NULL CHECK (scope IN ('record','project','team_system')),
    summary_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','reviewed','changes_requested','approved')),
    reviewer_id TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX monitoring_reviews_project_idx ON monitoring_reviews(project_id, scope, created_at);

CREATE TRIGGER monitoring_snapshots_no_update BEFORE UPDATE ON monitoring_snapshots BEGIN SELECT RAISE(ABORT, 'monitoring snapshots are append-only'); END;
CREATE TRIGGER monitoring_snapshots_guard_delete BEFORE DELETE ON monitoring_snapshots WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'monitoring snapshots are append-only'); END;
CREATE TRIGGER monitoring_snapshot_events_no_update BEFORE UPDATE ON monitoring_snapshot_events BEGIN SELECT RAISE(ABORT, 'monitoring snapshot events are append-only'); END;
CREATE TRIGGER monitoring_snapshot_events_guard_delete BEFORE DELETE ON monitoring_snapshot_events WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'monitoring snapshot events are append-only'); END;
CREATE TRIGGER monitoring_reviews_no_update BEFORE UPDATE ON monitoring_reviews BEGIN SELECT RAISE(ABORT, 'monitoring reviews are append-only'); END;
CREATE TRIGGER monitoring_reviews_guard_delete BEFORE DELETE ON monitoring_reviews WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'monitoring reviews are append-only'); END;
