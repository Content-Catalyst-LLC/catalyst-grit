# Catalyst Grit

**Current release: v1.5.0 — Learning Loops and Adaptation Patterns**

Catalyst Grit is a private-by-default human-systems recovery and learning engine. It documents setbacks, the conditions shaping recovery, owned actions, checkpoints, reassessments, retrospectives, and proposed system changes without scoring character, diagnosing health, or ranking people.

## v1.5.0 capabilities

- Structured retrospectives covering what happened, what was expected, what changed, what helped, what hindered, what was learned, what to repeat, what to redesign, and remaining uncertainty
- Explainable adaptation-pattern candidates with exact evidence paths and recorded values
- User review decisions to accept, reject, or correct a pattern before it is treated as useful project knowledge
- Project-level pattern aggregation across recovery records without personality labels or hidden inference
- Source-linked system-change proposals with owners, expected benefits, pilot windows, review results, and adopt/revise/defer/retire decisions
- Append-only retrospectives, pattern reviews, system-change events, action events, and record revisions
- Executable recovery plans with owned actions, four planning horizons, blockers, escalation, checkpoints, and reassessment triggers
- Pressure, constraint, support, capacity, control-zone, and friction-layer maps
- Persistent SQLite projects, revisions, checkpoints, reviews, audit history, retention, import, and export
- Public non-persistent browser demo and authenticated private WordPress workspace

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
```

Catalyst Grit is educational and analytical infrastructure. It is not diagnosis, mental-health advice, employee evaluation, automated eligibility, a personality assessment, or an outcome guarantee.
