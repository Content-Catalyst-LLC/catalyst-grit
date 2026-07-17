# Migration 007 — Monitoring, Trends, and Resilience Signals

Migration 007 adds append-only `monitoring_snapshots`, `monitoring_snapshot_events`, and `monitoring_reviews`. Existing projects, records, revisions, actions, checkpoints, evidence, assumptions, and handoffs are unchanged.

Snapshots preserve original calculation provenance and source revision hashes. Database triggers prevent update or unguarded deletion. Rollback removes only the v1.8 monitoring tables.
