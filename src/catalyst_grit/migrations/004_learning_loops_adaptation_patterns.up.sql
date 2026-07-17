CREATE TABLE retrospectives (
    retrospective_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES recovery_records(record_id) ON DELETE CASCADE,
    revision_id TEXT NOT NULL REFERENCES record_revisions(revision_id) ON DELETE CASCADE,
    content_json TEXT NOT NULL,
    uncertainties_json TEXT NOT NULL DEFAULT '[]',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(record_id, revision_id)
);
CREATE INDEX retrospectives_record_idx ON retrospectives(record_id, created_at);

CREATE TABLE pattern_reviews (
    pattern_review_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    pattern_key TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('accept','reject','correct')),
    corrected_label TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    actor_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX pattern_reviews_project_idx ON pattern_reviews(project_id, pattern_key, created_at);

CREATE TABLE system_changes (
    system_change_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    proposed_change TEXT NOT NULL,
    owner TEXT,
    expected_benefit TEXT NOT NULL DEFAULT '',
    pilot_start TEXT,
    pilot_end TEXT,
    review_result TEXT NOT NULL DEFAULT '',
    decision TEXT NOT NULL DEFAULT 'proposed' CHECK (decision IN ('proposed','piloting','adopt','revise','defer','retire')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX system_changes_project_idx ON system_changes(project_id, decision, created_at);

CREATE TABLE system_change_sources (
    system_change_id TEXT NOT NULL REFERENCES system_changes(system_change_id) ON DELETE CASCADE,
    record_id TEXT NOT NULL REFERENCES recovery_records(record_id) ON DELETE CASCADE,
    evidence_note TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(system_change_id, record_id)
);

CREATE TABLE system_change_events (
    event_id TEXT PRIMARY KEY,
    system_change_id TEXT NOT NULL REFERENCES system_changes(system_change_id) ON DELETE CASCADE,
    from_decision TEXT,
    to_decision TEXT NOT NULL,
    review_result TEXT NOT NULL DEFAULT '',
    actor_id TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX system_change_events_idx ON system_change_events(system_change_id, created_at);

CREATE TRIGGER retrospectives_no_update BEFORE UPDATE ON retrospectives BEGIN SELECT RAISE(ABORT, 'retrospectives are append-only'); END;
CREATE TRIGGER retrospectives_guard_delete BEFORE DELETE ON retrospectives WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'retrospectives are append-only'); END;
CREATE TRIGGER pattern_reviews_no_update BEFORE UPDATE ON pattern_reviews BEGIN SELECT RAISE(ABORT, 'pattern reviews are append-only'); END;
CREATE TRIGGER pattern_reviews_guard_delete BEFORE DELETE ON pattern_reviews WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'pattern reviews are append-only'); END;
CREATE TRIGGER system_change_events_no_update BEFORE UPDATE ON system_change_events BEGIN SELECT RAISE(ABORT, 'system change events are append-only'); END;
CREATE TRIGGER system_change_events_guard_delete BEFORE DELETE ON system_change_events WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'system change events are append-only'); END;
