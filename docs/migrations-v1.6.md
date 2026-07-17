# Workspace Migration 005 — Team Recovery and Facilitated Review

Migration 005 adds:

- `team_memberships`
- `facilitated_sessions`
- `session_participants`
- `team_perspectives`
- `facilitated_agreements`
- `facilitated_agreement_events`

Existing projects receive one active owner membership derived from `projects.owner_id`. Existing recovery records, revisions, actions, checkpoints, reviews, retrospectives, patterns, system changes, and audit history are not rewritten.

`team_perspectives` and `facilitated_agreement_events` are append-only. Their deletion guards are released only during an explicit repository purge transaction.

Rollback removes only the six v1.6 tables and their triggers. Earlier migrations remain intact.
