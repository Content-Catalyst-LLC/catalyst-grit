# Catalyst Grit

**Current release: v1.4.0 — Recovery Planning and Action Management**

Catalyst Grit is a private-by-default human-systems recovery and learning engine. It documents setbacks, the conditions shaping recovery, owned actions, checkpoints, reassessments, and learning without scoring character, diagnosing health, or ranking people.

## v1.4.0 capabilities

- Executable recovery plans with a smallest recoverable next step
- Named action owners, statuses, target dates, effort, urgency, required support, expected effects, and completion evidence
- 24-hour, 72-hour, 7-day, and longer-term planning horizons
- Action dependencies and unresolved external-dependency signals
- Continue, reduce-scope, pause, delegate, and escalate decisions
- Blocker records, escalation paths, and non-punitive past-target review signals
- Dated checkpoints, success signals, and reassessment triggers
- Append-only action events and reassessments that create new record revisions
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
grit record-map --database catalyst-grit.sqlite3 RECORD_ID
grit action-list --database catalyst-grit.sqlite3 RECORD_ID
grit action-update --database catalyst-grit.sqlite3 ACTION_ID --status in_progress
grit blocker-add --database catalyst-grit.sqlite3 RECORD_ID --title "Reviewer availability"
grit record-reassess --database catalyst-grit.sqlite3 RECORD_ID updated-request.json
```

Catalyst Grit is educational and analytical infrastructure. It is not diagnosis, mental-health advice, employee evaluation, automated eligibility, or an outcome guarantee.
