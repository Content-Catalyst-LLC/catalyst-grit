CREATE TABLE team_memberships (
    membership_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    member_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner','facilitator','contributor','reviewer','observer')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('invited','active','removed')),
    access_scope TEXT NOT NULL DEFAULT 'shared' CHECK (access_scope IN ('shared','facilitation_only')),
    consent_status TEXT NOT NULL DEFAULT 'pending' CHECK (consent_status IN ('pending','granted','withdrawn')),
    joined_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, member_key)
);
CREATE INDEX team_memberships_project_idx ON team_memberships(project_id, role, status);

INSERT INTO team_memberships(
    membership_id, project_id, member_key, display_name, role, status,
    access_scope, consent_status, joined_at, created_at, updated_at
)
SELECT 'cgm_' || lower(hex(randomblob(16))), project_id, owner_id, owner_id,
       'owner', 'active', 'shared', 'granted', created_at, created_at, updated_at
FROM projects;

CREATE TABLE facilitated_sessions (
    session_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    record_id TEXT REFERENCES recovery_records(record_id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','in_progress','completed','cancelled')),
    facilitator_key TEXT NOT NULL,
    scheduled_for TEXT,
    started_at TEXT,
    completed_at TEXT,
    ground_rules_json TEXT NOT NULL DEFAULT '[]',
    agenda_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX facilitated_sessions_project_idx ON facilitated_sessions(project_id, status, scheduled_for);

CREATE TABLE session_participants (
    session_id TEXT NOT NULL REFERENCES facilitated_sessions(session_id) ON DELETE CASCADE,
    membership_id TEXT NOT NULL REFERENCES team_memberships(membership_id) ON DELETE CASCADE,
    participation_status TEXT NOT NULL DEFAULT 'invited' CHECK (participation_status IN ('invited','confirmed','declined','attended','absent')),
    consent_status TEXT NOT NULL DEFAULT 'pending' CHECK (consent_status IN ('pending','granted','withdrawn')),
    sharing_scope TEXT NOT NULL DEFAULT 'shared' CHECK (sharing_scope IN ('shared','facilitator_only','private')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(session_id, membership_id)
);

CREATE TABLE team_perspectives (
    perspective_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    session_id TEXT REFERENCES facilitated_sessions(session_id) ON DELETE SET NULL,
    record_id TEXT REFERENCES recovery_records(record_id) ON DELETE SET NULL,
    membership_id TEXT REFERENCES team_memberships(membership_id) ON DELETE SET NULL,
    contributor_label TEXT NOT NULL DEFAULT '',
    perspective_type TEXT NOT NULL CHECK (perspective_type IN ('impact','pressure','constraint','support','capacity','response','learning','other')),
    content TEXT NOT NULL,
    sharing_scope TEXT NOT NULL DEFAULT 'shared' CHECK (sharing_scope IN ('shared','facilitator_only','private')),
    consent_status TEXT NOT NULL DEFAULT 'granted' CHECK (consent_status IN ('pending','granted','withdrawn')),
    source_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX team_perspectives_project_idx ON team_perspectives(project_id, session_id, perspective_type, created_at);

CREATE TABLE facilitated_agreements (
    agreement_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES facilitated_sessions(session_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    owner_key TEXT,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','accepted','in_progress','completed','blocked','retired')),
    completion_evidence TEXT NOT NULL DEFAULT '',
    support_needed TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX facilitated_agreements_session_idx ON facilitated_agreements(session_id, status, due_date);

CREATE TABLE facilitated_agreement_events (
    event_id TEXT PRIMARY KEY,
    agreement_id TEXT NOT NULL REFERENCES facilitated_agreements(agreement_id) ON DELETE CASCADE,
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX facilitated_agreement_events_idx ON facilitated_agreement_events(agreement_id, created_at);

CREATE TRIGGER team_perspectives_no_update BEFORE UPDATE ON team_perspectives BEGIN SELECT RAISE(ABORT, 'team perspectives are append-only'); END;
CREATE TRIGGER team_perspectives_guard_delete BEFORE DELETE ON team_perspectives WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'team perspectives are append-only'); END;
CREATE TRIGGER facilitated_agreement_events_no_update BEFORE UPDATE ON facilitated_agreement_events BEGIN SELECT RAISE(ABORT, 'agreement events are append-only'); END;
CREATE TRIGGER facilitated_agreement_events_guard_delete BEFORE DELETE ON facilitated_agreement_events WHEN cg_allow_purge() = 0 BEGIN SELECT RAISE(ABORT, 'agreement events are append-only'); END;
