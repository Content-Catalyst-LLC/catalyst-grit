# Workspace migrations — v1.2.0

Catalyst Grit packages ordered reversible SQL migrations inside the Python wheel.

1. `001_core_workspace` creates projects, records, revisions, and status history.
2. `002_checkpoints_reviews_audit` adds actions, checkpoints, reviews, audit events, and append-only triggers.

`grit init` applies all pending migrations. `grit migrate --target N` moves to an explicit version. `grit rollback --steps N` reverses the most recently applied migrations. Migration state is recorded in `schema_migrations`.

Before rollback or source installation, back up the SQLite database. Rolling back a populated schema intentionally removes the tables introduced by the reversed migration.
