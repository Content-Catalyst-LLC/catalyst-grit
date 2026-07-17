# Workspace migration 003 — v1.4.0

Migration `003_recovery_plans_actions_reassessment` upgrades an existing v1.2/v1.3 SQLite workspace in place.

## Added action fields

`action_key`, `horizon`, `expected_effect`, required-support JSON, dependency JSON, `effort`, `urgency`, `completion_evidence`, `reassessment_trigger`, `blocked_reason`, `escalation_path`, `completed_at`, and `updated_at`.

## Added tables

- `action_events`: append-only action state and evidence history.
- `blockers`: support, dependency, ownership, status, and escalation tracking.
- `reassessments`: append-only links between prior and newly generated revisions, including plan comparison data.

Database triggers reject update or deletion of action events and reassessments during ordinary operation. Guarded permanent record purge remains the only intentional history-removal path.

The installer preserves local `.db`, `.sqlite`, and `.sqlite3` files, then the repository opens them through the ordered migration manager. The migration can roll back to level 2 and reapply to level 3 in the release tests.
