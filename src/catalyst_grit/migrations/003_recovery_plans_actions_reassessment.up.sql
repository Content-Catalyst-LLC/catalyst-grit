ALTER TABLE actions ADD COLUMN action_key TEXT NOT NULL DEFAULT '';
ALTER TABLE actions ADD COLUMN horizon TEXT NOT NULL DEFAULT '7_days' CHECK (horizon IN ('24_hours','72_hours','7_days','longer_term'));
ALTER TABLE actions ADD COLUMN expected_effect TEXT NOT NULL DEFAULT '';
ALTER TABLE actions ADD COLUMN required_support_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE actions ADD COLUMN dependencies_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE actions ADD COLUMN effort REAL NOT NULL DEFAULT 3 CHECK (effort BETWEEN 1 AND 5);
ALTER TABLE actions ADD COLUMN urgency REAL NOT NULL DEFAULT 3 CHECK (urgency BETWEEN 1 AND 5);
ALTER TABLE actions ADD COLUMN completion_evidence TEXT NOT NULL DEFAULT '';
ALTER TABLE actions ADD COLUMN reassessment_trigger TEXT NOT NULL DEFAULT '';
ALTER TABLE actions ADD COLUMN blocked_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE actions ADD COLUMN escalation_path TEXT NOT NULL DEFAULT '';
ALTER TABLE actions ADD COLUMN completed_at TEXT;
ALTER TABLE actions ADD COLUMN updated_at TEXT;

UPDATE actions SET action_key = source_section || '-' || printf('%03d', ordinal + 1), updated_at = created_at WHERE action_key = '';
CREATE INDEX actions_status_idx ON actions(record_id, status, target_date);

CREATE TABLE action_events (
    event_id TEXT PRIMARY KEY,
    action_id TEXT NOT NULL REFERENCES actions(action_id) ON DELETE CASCADE,
    record_id TEXT NOT NULL REFERENCES recovery_records(record_id) ON DELETE CASCADE,
    revision_id TEXT NOT NULL REFERENCES record_revisions(revision_id) ON DELETE CASCADE,
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    blocked_reason TEXT NOT NULL DEFAULT '',
    completion_evidence TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX action_events_action_idx ON action_events(action_id, created_at);
CREATE INDEX action_events_record_idx ON action_events(record_id, created_at);

CREATE TABLE blockers (
    blocker_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES recovery_records(record_id) ON DELETE CASCADE,
    action_id TEXT REFERENCES actions(action_id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','escalated')),
    owner TEXT,
    required_support TEXT NOT NULL DEFAULT '',
    escalation_path TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE INDEX blockers_record_idx ON blockers(record_id, status, created_at);

CREATE TABLE reassessments (
    reassessment_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES recovery_records(record_id) ON DELETE CASCADE,
    checkpoint_id TEXT REFERENCES checkpoints(checkpoint_id) ON DELETE SET NULL,
    from_revision_id TEXT NOT NULL REFERENCES record_revisions(revision_id),
    to_revision_id TEXT NOT NULL REFERENCES record_revisions(revision_id),
    observed_summary TEXT NOT NULL,
    changed_assumptions_json TEXT NOT NULL DEFAULT '[]',
    planned_vs_observed_json TEXT NOT NULL DEFAULT '{}',
    carried_actions_json TEXT NOT NULL DEFAULT '[]',
    actor_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX reassessments_record_idx ON reassessments(record_id, created_at);

CREATE TRIGGER action_events_no_update BEFORE UPDATE ON action_events BEGIN SELECT RAISE(ABORT, 'action events are append-only'); END;
CREATE TRIGGER action_events_guard_delete BEFORE DELETE ON action_events WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'action events are append-only'); END;
CREATE TRIGGER reassessments_no_update BEFORE UPDATE ON reassessments BEGIN SELECT RAISE(ABORT, 'reassessments are append-only'); END;
CREATE TRIGGER reassessments_guard_delete BEFORE DELETE ON reassessments WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'reassessments are append-only'); END;
