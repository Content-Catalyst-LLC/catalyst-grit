# Persistent workspace

Catalyst Grit v1.2.0 adds a private, local-first SQLite workspace behind the canonical recovery-record engine.

## Entities

- recovery projects
- recovery records
- append-only record revisions
- revision-scoped actions
- review checkpoints
- human review events
- status history
- audit events

Every project and record is created with `visibility = private`. The public WordPress demo remains client-side and non-persistent.

## Repository abstraction

`SQLiteWorkspaceRepository` owns persistence operations. Application code should not write workspace tables directly. This boundary allows a later PostgreSQL repository to preserve the same operations without changing the domain engine.

## Revision behavior

Each changed record creates a new `record_revisions` row containing:

- the exact canonical output;
- the accepted request snapshot;
- schema and engine versions;
- a SHA-256 content digest;
- actor, reason, and creation time.

Database triggers reject revision updates and ordinary deletion. `purge_record(confirm=True)` temporarily enables a guarded cascade for explicit privacy deletion and leaves a content-free tombstone audit event.

## Retention and deletion

- `delete_record` performs a reversible visibility-safe soft deletion.
- `set_retention` assigns an ISO date or duration.
- `purge_due_records` permanently removes due record content.
- `purge_record` refuses to run without explicit confirmation.

## Import and export

The repository accepts:

- v1.0.x flat requests;
- v1.1 and v1.2 nested requests;
- canonical recovery records;
- `catalyst-grit-workspace/1.0` bundles.

Workspace exports include the current record, all revisions, actions, checkpoints, reviews, status history, and audit events. A fresh repository import preserves the exact canonical records and their original engine provenance.
