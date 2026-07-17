# Catalyst Grit

**Current release: v1.9.0 — Publication, Export, API, and Institutional Integration**

Catalyst Grit is a private, structured human-systems recovery and learning environment. It documents setbacks, conditions, actions, evidence, assumptions, team review, learning, monitoring, and institutional handoffs without diagnosing, ranking, or predicting people.

## v1.9.0 capabilities

- Seven governed publication types: recovery brief, facilitated-review brief, action plan, learning-loop report, adaptation proposal, monitoring summary, and Decision Studio handoff packet
- Canonical JSON, JSON-LD, Markdown, HTML, approved tabular CSV, platform PDF-render requests, and deterministic publication bundles
- Private, internal, and public redaction policies with deterministic masking and human-review requirements
- Framework-neutral institutional API with bearer-token hashing, scopes, project allowlists, rate limits, and append-only request audits
- Read routes for records, revisions, actions, checkpoints, reviews, evidence, patterns, monitoring, handoffs, and audit history
- Versioned retention, export/redaction, access-review, methodology-governance, and schema-deprecation policies
- Append-only access reviews and publication lifecycle events
- Methodology registry, schema compatibility checks, and administrative diagnostics
- Migration 008 with complete compatibility for v1.0.x through v1.8.0 workspaces

## Governance boundaries

Catalyst Grit is not mental-health advice, diagnosis, character scoring, personality inference, employee ranking, hidden performance evaluation, automated eligibility, or an outcome guarantee. Public and internal publication artifacts require human review.

## Quick validation

```bash
python3 scripts/release_contract.py
```

## CLI examples

```bash
grit init --database catalyst-grit.sqlite3
grit project-create --database catalyst-grit.sqlite3 --title "Recovery project"
grit record-save --database catalyst-grit.sqlite3 PROJECT_ID examples/grit_record_input.json

grit publication-generate --database catalyst-grit.sqlite3 \
  PROJECT_ID recovery_brief --record RECORD_ID \
  --format markdown --redaction internal --output recovery-brief.md

grit api-client-create --database catalyst-grit.sqlite3 \
  --name "Institutional reader" --scope records:read --project PROJECT_ID

grit policy-set --database catalyst-grit.sqlite3 \
  export_redaction policy.json --project PROJECT_ID

grit institution-diagnostics --database catalyst-grit.sqlite3
```

## WordPress

- `[catalyst_grit_demo]` — non-persistent public recovery-record demo
- `[catalyst_grit_workspace]` — authenticated per-user private workspace with publication and governance guidance

## Architecture

The installable Python package contains the canonical engine, persistence, publication, and API service contracts. SQLite is the portable private-workspace implementation. The institutional API is framework-neutral so deployments can attach it to an approved web layer without duplicating domain authorization.

See `docs/` for the record contract, persistence, monitoring, publication, API, governance, migration, and integration specifications.
