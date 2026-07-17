# Export Specification

Catalyst Grit v1.8.0 exports canonical JSON, an optional Markdown review brief, private `catalyst-grit-workspace/1.0` bundles, and a Decision Studio handoff packet.

Record workspace exports preserve revisions, actions, action events, blockers, reassessments, retrospectives, checkpoints, reviews, team perspectives, evidence items and review events, assumptions and lifecycle events, handoffs and validation events, status history, and audit events.

Project exports additionally preserve pattern reviews, system changes, team memberships, facilitated sessions, agreements, the evidence ledger, assumption matrix, and all cross-product handoffs. Import restores supported traceability records into a clean workspace and records new import audit history rather than rewriting source history.

The Decision Studio packet uses `sustainable-catalyst-decision-handoff/1.0` and preserves source record and revision IDs, canonical hash, recovery context, action state, evidence, assumptions, human review, review history, and decision guardrails.

Exports are private analytical and workflow records. They are not diagnostic records, employee ratings, personality profiles, automated eligibility records, or predictions.
