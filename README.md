# Catalyst Grit

**Current release: v1.7.0 — Evidence, Assumptions, and Decision Handoffs**

Catalyst Grit is a private-by-default human-systems recovery and learning engine. It documents setbacks, the conditions shaping recovery, owned actions, checkpoints, reassessments, retrospectives, and proposed system changes without scoring character, diagnosing health, or ranking people.

## v1.7.0 capabilities

- Traceable evidence notes, source links, file references, quotes, observations, datasets, calculations, analyses, experiment results, methods, and reference documents
- Evidence strength, review state, content hashes, provenance chains, source products and versions, and append-only review events
- Explicit assumptions with uncertainty, confidence, owners, review dates, source paths, and lifecycle events
- Evidence links that support, challenge, contextualize, derive from, or conflict with records, assumptions, actions, checkpoints, agreements, system changes, and handoffs
- Stable cross-product handoff artifacts for Catalyst Canvas, Catalyst Data, Workbench, Sustainable Catalyst Lab, Decision Studio, Knowledge Library, and Research Librarian
- Read-only snapshot and live-reference modes with import validation, stale-reference handling, conflict detection, and append-only events
- Provenance-preserving Decision Studio packets carrying recovery context, actions, tradeoffs, evidence, assumptions, and review state
- All v1.0 through v1.6 recovery, planning, learning, persistence, team, facilitation, privacy, retention, audit, and export capabilities

## Quick validation

```bash
python3 scripts/release_contract.py
```

## CLI

```bash
grit generate examples/grit_record_input.json
grit init --database catalyst-grit.sqlite3
grit project-create --database catalyst-grit.sqlite3 --title "Recovery project"
grit record-save --database catalyst-grit.sqlite3 PROJECT_ID examples/grit_record_input.json
grit retrospective-list --database catalyst-grit.sqlite3 RECORD_ID
grit pattern-list --database catalyst-grit.sqlite3 PROJECT_ID --include-singletons
grit pattern-review --database catalyst-grit.sqlite3 PROJECT_ID PATTERN_KEY --decision accept
grit system-change-add --database catalyst-grit.sqlite3 PROJECT_ID \
  --title "Revise handoff" --proposed-change "Add an explicit decision owner" \
  --source-record RECORD_ID
grit system-change-update --database catalyst-grit.sqlite3 SYSTEM_CHANGE_ID \
  --decision piloting --pilot-start 2026-07-20 --pilot-end 2026-08-03
grit team-member-add --database catalyst-grit.sqlite3 PROJECT_ID \
  --member-key facilitator-1 --display-name "Facilitator One" \
  --role facilitator --status active --consent-status granted
grit session-create --database catalyst-grit.sqlite3 PROJECT_ID \
  --title "Recovery review" --facilitator facilitator-1
grit perspective-add --database catalyst-grit.sqlite3 PROJECT_ID \
  --session SESSION_ID --member-key facilitator-1 --type constraint \
  --content "Approval ownership is unclear" --actor facilitator-1
grit agreement-add --database catalyst-grit.sqlite3 SESSION_ID \
  --title "Name the decision owner" --owner-key facilitator-1 --actor facilitator-1
grit evidence-add --database catalyst-grit.sqlite3 PROJECT_ID \
  --record RECORD_ID --type dataset --title "Cycle-time observations" \
  --source-product "Catalyst Data" --source-version 1.12.0 --artifact-id dataset-42
grit assumption-add --database catalyst-grit.sqlite3 PROJECT_ID \
  --record RECORD_ID --statement "The reviewer is available this week" --confidence 40
grit decision-handoff --database catalyst-grit.sqlite3 RECORD_ID --output decision-handoff.json
```

Catalyst Grit is educational and analytical infrastructure. It is not diagnosis, mental-health advice, employee evaluation, automated eligibility, a personality assessment, or an outcome guarantee.
