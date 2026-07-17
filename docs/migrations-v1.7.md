# Migration 006 — Evidence, Assumptions, and Decision Handoffs

Migration 006 adds:

- `evidence_items`, `evidence_events`, and `evidence_links`;
- `assumptions` and `assumption_events`; and
- `handoff_artifacts` and `handoff_events`.

Evidence, assumption, and handoff events are append-only and protected by database triggers. Existing projects, records, revisions, plans, learning loops, team memberships, facilitated sessions, perspectives, agreements, reviews, audit events, and local workspace files are not rewritten.

Rollback removes only the migration 006 tables and triggers. Migrations 001 through 005 remain intact.
