CREATE TABLE actions (
    action_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES recovery_records(record_id) ON DELETE CASCADE,
    revision_id TEXT NOT NULL REFERENCES record_revisions(revision_id) ON DELETE CASCADE,
    source_section TEXT NOT NULL CHECK (source_section IN ('response','next_steps')),
    ordinal INTEGER NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    owner TEXT,
    target_date TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(revision_id, source_section, ordinal)
);
CREATE INDEX actions_record_idx ON actions(record_id, revision_id);

CREATE TABLE checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    record_id TEXT REFERENCES recovery_records(record_id) ON DELETE CASCADE,
    revision_id TEXT REFERENCES record_revisions(revision_id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    scheduled_for TEXT,
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','due','completed','cancelled')),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX checkpoints_project_idx ON checkpoints(project_id, scheduled_for);
CREATE INDEX checkpoints_record_idx ON checkpoints(record_id, scheduled_for);

CREATE TABLE reviews (
    review_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES recovery_records(record_id) ON DELETE CASCADE,
    revision_id TEXT NOT NULL REFERENCES record_revisions(revision_id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX reviews_record_idx ON reviews(record_id, created_at);

CREATE TABLE audit_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX audit_events_entity_idx ON audit_events(entity_type, entity_id, created_at);

CREATE TRIGGER record_revisions_no_update
BEFORE UPDATE ON record_revisions
BEGIN
  SELECT RAISE(ABORT, 'record revisions are append-only');
END;

CREATE TRIGGER record_revisions_guard_delete
BEFORE DELETE ON record_revisions
WHEN cg_allow_purge() = 0
BEGIN
  SELECT RAISE(ABORT, 'record revisions are append-only');
END;

CREATE TRIGGER status_history_no_update
BEFORE UPDATE ON status_history
BEGIN
  SELECT RAISE(ABORT, 'status history is append-only');
END;

CREATE TRIGGER status_history_guard_delete
BEFORE DELETE ON status_history
WHEN cg_allow_purge() = 0
BEGIN
  SELECT RAISE(ABORT, 'status history is append-only');
END;

CREATE TRIGGER reviews_no_update
BEFORE UPDATE ON reviews
BEGIN
  SELECT RAISE(ABORT, 'reviews are append-only');
END;

CREATE TRIGGER reviews_guard_delete
BEFORE DELETE ON reviews
WHEN cg_allow_purge() = 0
BEGIN
  SELECT RAISE(ABORT, 'reviews are append-only');
END;

CREATE TRIGGER audit_events_no_update
BEFORE UPDATE ON audit_events
BEGIN
  SELECT RAISE(ABORT, 'audit events are append-only');
END;

CREATE TRIGGER audit_events_guard_delete
BEFORE DELETE ON audit_events
WHEN cg_allow_purge() = 0
BEGIN
  SELECT RAISE(ABORT, 'audit events are append-only');
END;
