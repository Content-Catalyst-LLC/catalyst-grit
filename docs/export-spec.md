# Export Specification

Catalyst Grit v1.9.0 separates private workspace portability from governed publication.

## Workspace bundles

`catalyst-grit-workspace/1.0` preserves projects, canonical records, immutable revisions, actions and events, blockers, reassessments, retrospectives, checkpoints, reviews, team participation, facilitated sessions, perspectives, agreements, evidence, assumptions, handoffs, monitoring snapshots and reviews, institutional policies, access reviews, publication metadata, methodology registrations, schema compatibility, status history, and audit history.

Workspace imports create new local audit history and do not rewrite the source bundle.

## Publication artifacts

`catalyst-grit-publication/1.0` supports recovery briefs, facilitated-review briefs, action plans, learning-loop reports, adaptation proposals, monitoring summaries, and Decision Studio handoff packets.

Outputs are canonical JSON, JSON-LD, Markdown, HTML, approved tabular CSV, a PDF-render request for the Sustainable Catalyst publication layer, and `catalyst-grit-publication-bundle/1.0` ZIP archives. Publication bundles include every supported rendering, a manifest, and SHA-256 checksums.

Private, internal, and public redaction policies are deterministic. Internal and public artifacts mask identity-bearing fields. Public artifacts additionally remove raw user input, private perspectives, direct source locations, and internal audit/provenance detail unless separately approved.

## Decision Studio handoff

The Decision Studio packet uses `sustainable-catalyst-decision-handoff/1.0` and preserves source record and revision IDs, canonical hashes, recovery context, action state, evidence, assumptions, human review, and decision guardrails.
