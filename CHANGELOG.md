# Changelog

## 1.4.0 — Recovery Planning and Action Management

- Added executable recovery plans with owned actions, four planning horizons, dependencies, expected effects, support requirements, effort, urgency, evidence, and reassessment triggers.
- Added explicit scope decisions, blockers, escalation paths, checkpoints, due-for-review signals, and the smallest recoverable next step.
- Added migration 003 with enriched actions, append-only action events, blockers, and reassessments.
- Added action, blocker, and reassessment CLI workflows plus plan-history export.
- Added public browser planning controls and plan summaries while preserving the non-persistent public boundary.
- Preserved checksum-based installation and existing private SQLite workspace files.

## 1.3.0 — Pressure, Constraint, Support, and Capacity Mapping

- Added inspectable condition maps, source-linked flags, completeness, contradiction detection, and accessible mapping controls.
- Preserved persistence, revision, import/export, and checksum-safe installation.

## 1.2.0 — Persistent Records, Projects, and Review Checkpoints

- Added a private SQLite workspace and packaged migration framework.
- Added projects, records, append-only revisions, actions, checkpoints, reviews, status history, and audit events.
- Added reopen, revision comparison, duplication, archive, soft deletion, retention, and guarded purge workflows.
- Added v1.0/v1.1/v1.2 import plus full workspace export/import.
- Added database and workspace CLI commands.
- Added an authenticated nonce-protected WordPress workspace while keeping the public demo non-persistent.
- Added persistence, migration, authorization, restart, revision, and round-trip release tests.

## 1.1.0 — Canonical Recovery Record Contract and Shared Engine

- Added the nested canonical recovery record, shared engine, methodology profile, browser parity, schemas, OpenAPI contract, and structured validation.

## 1.0.1 — Repository Integrity and Product Consolidation

- Consolidated the recovery-record product and archived the legacy trait-metrics prototype.
