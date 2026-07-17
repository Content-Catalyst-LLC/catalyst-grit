CREATE TABLE evidence_items (
    evidence_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    record_id TEXT REFERENCES recovery_records(record_id) ON DELETE SET NULL,
    revision_id TEXT REFERENCES record_revisions(revision_id) ON DELETE SET NULL,
    evidence_type TEXT NOT NULL CHECK (evidence_type IN ('note','source_link','file_reference','quote','observation','dataset','calculation','analysis','experiment_result','method','reference_document')),
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    source_uri TEXT NOT NULL DEFAULT '',
    source_artifact_id TEXT NOT NULL DEFAULT '',
    source_product TEXT NOT NULL DEFAULT '',
    source_version TEXT NOT NULL DEFAULT '',
    provenance_json TEXT NOT NULL DEFAULT '[]',
    strength TEXT NOT NULL DEFAULT 'unknown' CHECK (strength IN ('unknown','weak','moderate','strong')),
    review_state TEXT NOT NULL DEFAULT 'unreviewed' CHECK (review_state IN ('unreviewed','accepted','questioned','rejected')),
    observed_at TEXT,
    added_by TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX evidence_items_project_idx ON evidence_items(project_id, record_id, evidence_type, review_state, created_at);

CREATE TABLE evidence_events (
    event_id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL REFERENCES evidence_items(evidence_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('created','reviewed','corrected','stale','conflict_recorded')),
    from_state TEXT,
    to_state TEXT,
    actor_id TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX evidence_events_idx ON evidence_events(evidence_id, created_at);

CREATE TABLE assumptions (
    assumption_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    record_id TEXT REFERENCES recovery_records(record_id) ON DELETE SET NULL,
    statement TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','validated','rejected','retired')),
    uncertainty TEXT NOT NULL DEFAULT '',
    confidence INTEGER NOT NULL DEFAULT 50 CHECK (confidence BETWEEN 0 AND 100),
    owner TEXT,
    review_due TEXT,
    source_paths_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX assumptions_project_idx ON assumptions(project_id, record_id, status, review_due);

CREATE TABLE assumption_events (
    event_id TEXT PRIMARY KEY,
    assumption_id TEXT NOT NULL REFERENCES assumptions(assumption_id) ON DELETE CASCADE,
    from_status TEXT,
    to_status TEXT NOT NULL,
    confidence INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    actor_id TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX assumption_events_idx ON assumption_events(assumption_id, created_at);

CREATE TABLE evidence_links (
    link_id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL REFERENCES evidence_items(evidence_id) ON DELETE CASCADE,
    target_type TEXT NOT NULL CHECK (target_type IN ('record','revision','assumption','action','checkpoint','system_change','agreement','handoff')),
    target_id TEXT NOT NULL,
    relation TEXT NOT NULL CHECK (relation IN ('supports','challenges','context','derived_from','conflicts_with')),
    notes TEXT NOT NULL DEFAULT '',
    actor_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(evidence_id,target_type,target_id,relation)
);
CREATE INDEX evidence_links_target_idx ON evidence_links(target_type, target_id, relation);

CREATE TABLE handoff_artifacts (
    handoff_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    record_id TEXT REFERENCES recovery_records(record_id) ON DELETE SET NULL,
    direction TEXT NOT NULL CHECK (direction IN ('inbound','outbound')),
    source_product TEXT NOT NULL,
    source_version TEXT NOT NULL,
    target_product TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    reference_mode TEXT NOT NULL DEFAULT 'snapshot' CHECK (reference_mode IN ('snapshot','live_reference')),
    source_uri TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    provenance_json TEXT NOT NULL DEFAULT '[]',
    content_hash TEXT NOT NULL,
    validation_state TEXT NOT NULL DEFAULT 'valid' CHECK (validation_state IN ('valid','invalid','stale','conflict')),
    stale_after TEXT,
    last_checked_at TEXT,
    conflict_notes TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_product, artifact_id, content_hash, target_product)
);
CREATE INDEX handoff_artifacts_project_idx ON handoff_artifacts(project_id, record_id, target_product, validation_state, created_at);

CREATE TABLE handoff_events (
    event_id TEXT PRIMARY KEY,
    handoff_id TEXT NOT NULL REFERENCES handoff_artifacts(handoff_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('created','validated','marked_stale','conflict_recorded','refreshed','exported')),
    from_state TEXT,
    to_state TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX handoff_events_idx ON handoff_events(handoff_id, created_at);

CREATE TRIGGER evidence_events_no_update BEFORE UPDATE ON evidence_events BEGIN SELECT RAISE(ABORT, 'evidence events are append-only'); END;
CREATE TRIGGER evidence_events_guard_delete BEFORE DELETE ON evidence_events WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'evidence events are append-only'); END;
CREATE TRIGGER assumption_events_no_update BEFORE UPDATE ON assumption_events BEGIN SELECT RAISE(ABORT, 'assumption events are append-only'); END;
CREATE TRIGGER assumption_events_guard_delete BEFORE DELETE ON assumption_events WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'assumption events are append-only'); END;
CREATE TRIGGER handoff_events_no_update BEFORE UPDATE ON handoff_events BEGIN SELECT RAISE(ABORT, 'handoff events are append-only'); END;
CREATE TRIGGER handoff_events_guard_delete BEFORE DELETE ON handoff_events WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'handoff events are append-only'); END;
