# Catalyst Grit

**Current release: v1.6.0 — Team Recovery and Facilitated Review**

Catalyst Grit is a private-by-default human-systems recovery and learning engine. It documents setbacks, the conditions shaping recovery, owned actions, checkpoints, reassessments, retrospectives, and proposed system changes without scoring character, diagnosing health, or ranking people.

## v1.6.0 capabilities

- Explicit project team roles: owner, facilitator, contributor, reviewer, and observer
- Consent-aware participation with invited, confirmed, declined, attended, and absent states
- Facilitated review sessions with purpose, agenda, ground rules, schedule, linked records, and lifecycle status
- Append-only team perspectives with shared, facilitator-only, and private scopes
- Shared agreements with owners, due dates, support needs, completion evidence, and append-only events
- Team recovery summaries that aggregate work conditions and agreement states without individual scores or rankings
- Project export/import for team members, sessions, perspectives, participants, and agreements
- Structured retrospectives, adaptation-pattern review, and source-linked system-change pilots
- Executable recovery plans, condition maps, persistent revisions, checkpoints, reviews, audit history, retention, and import/export
- Public non-persistent browser demo and authenticated private WordPress workspace with v1.5 workspace migration

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
```

Catalyst Grit is educational and analytical infrastructure. It is not diagnosis, mental-health advice, employee evaluation, automated eligibility, a personality assessment, or an outcome guarantee.
