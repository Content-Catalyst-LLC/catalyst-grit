# Workspace migration 004 — v1.5.0

Migration `004_learning_loops_adaptation_patterns` adds the persistent learning layer to an existing Catalyst Grit workspace.

## Added tables

- `retrospectives` — one immutable generated retrospective per record revision
- `pattern_reviews` — append-only accept, reject, or correct decisions with the evidence visible at review time
- `system_changes` — current source-linked process or system-change proposal state
- `system_change_sources` — links proposals to recovery records and evidence notes
- `system_change_events` — immutable proposal and pilot decision history

Database triggers prevent update or deletion of retrospectives, pattern reviews, and system-change events during normal operation. Guarded repository purge remains the only permitted destructive path for records covered by an explicit retention operation.

The migration is ordered after migrations 001–003 and supports rollback followed by clean remigration. Existing projects, records, revisions, actions, checkpoints, reviews, and SQLite files are preserved by the installer.
