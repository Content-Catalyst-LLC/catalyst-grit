# Catalyst Grit

**Current release: v2.0.0 — Connected Human-Systems Resilience Platform**

Catalyst Grit is a private, structured human-systems recovery and learning environment. It connects setbacks, conditions, actions, checkpoints, evidence, learning, decisions, monitoring, and governed publication without diagnosing, ranking, predicting, or automating decisions about people.

## v2.0.0 capabilities

- Twelve-stage connected workflow from setback through publication
- Provenance-preserving artifact graph across Sustainable Catalyst products
- Human-review gates for assessment, reassessment, learning, adaptation, decision handoff, monitoring, and publication
- Offline-verifiable portable project snapshots and restore
- Connected-platform API routes with explicit read, write, review, and export scopes
- Cross-product synchronization history and conflict visibility
- Accessible WordPress workflow summary with responsive cards, live status, visible focus, and reduced-motion support
- Migration 009 with compatibility for existing v1.0.x through v1.9.0 workspaces
- All v1.9 publication, export, institutional API, policy, access-review, methodology, and schema-governance capabilities retained

## Governance boundaries

Catalyst Grit is not mental-health advice, diagnosis, character scoring, personality inference, employee ranking, hidden performance evaluation, automated eligibility, or an outcome guarantee. Connected workflow completion never substitutes for human judgment.

## Quick validation

```bash
python3 scripts/release_contract.py
```

## CLI examples

```bash
grit init --database catalyst-grit.sqlite3
grit project-create --database catalyst-grit.sqlite3 --title "Recovery project"
grit record-save --database catalyst-grit.sqlite3 PROJECT_ID examples/grit_record_input.json

grit platform-workflow-start --database catalyst-grit.sqlite3 RECORD_ID --actor owner
grit platform-overview --database catalyst-grit.sqlite3 PROJECT_ID
grit platform-snapshot --database catalyst-grit.sqlite3 PROJECT_ID --record RECORD_ID --output portable-project.json
grit platform-verify portable-project.json
```

## WordPress

- `[catalyst_grit_demo]` — non-persistent public recovery-record demo
- `[catalyst_grit_workspace]` — authenticated per-user connected resilience workspace

See `docs/connected-platform.md`, `docs/accessibility-portability.md`, and the remaining `docs/` specifications.
