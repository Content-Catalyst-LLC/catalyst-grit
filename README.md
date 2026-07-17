# Catalyst Grit

**Current release: v1.2.0 — Persistent Records, Projects, and Review Checkpoints**

Catalyst Grit is a Sustainable Catalyst human-systems module for documenting setbacks, recovery conditions, response choices, learning, and review checkpoints. It evaluates recovery conditions—not character, worth, motivation, or clinical state.

## v1.2 private workspace

The installable package now includes a local-first SQLite repository with:

- private recovery projects and records;
- append-only revisions with exact inputs, outputs, versions, hashes, actors, and reasons;
- saved actions, checkpoints, human reviews, status history, and audit events;
- reopen, compare, duplicate, archive, delete, retention, and guarded purge operations;
- v1.0/v1.1/v1.2 import and `catalyst-grit-workspace/1.0` export/import;
- ordered reversible migrations packaged inside the Python wheel.

The canonical recovery record still contains `metadata`, `user_input`, `normalized_input`, `findings`, `human_review`, and `extensions`. The `cg-recovery-conditions@1.2.0` methodology remains explainable and non-diagnostic.

## Install and validate

```bash
python3 -m pip install -e '.[dev]'
python3 scripts/release_contract.py
```

## Generate a one-time record

```bash
grit validate examples/grit_record_input.json
grit generate examples/grit_record_input.json --format json
grit generate examples/grit_record_input.json --format markdown
```

## Create a private workspace

```bash
grit init --database ~/catalyst-grit.sqlite3
grit project-create --database ~/catalyst-grit.sqlite3 --title "Reporting recovery"
grit record-save --database ~/catalyst-grit.sqlite3 PROJECT_ID examples/grit_record_input.json
grit record-show --database ~/catalyst-grit.sqlite3 RECORD_ID --canonical
grit checkpoint-add --database ~/catalyst-grit.sqlite3 PROJECT_ID --record RECORD_ID --title "72-hour review" --date 2026-07-20
grit workspace-export --database ~/catalyst-grit.sqlite3 --record RECORD_ID --output recovery-workspace.json
```

Use `grit --help` for revision comparison, duplication, archiving, deletion, retention, purge, review, migration, and import commands.

## WordPress

- `[catalyst_grit_demo]` — public browser demo; no persistence by default.
- `[catalyst_grit_workspace]` — authenticated private per-user workspace with nonce-protected save, load, and delete actions.

## Boundaries

Catalyst Grit is educational and analytical infrastructure. It is not mental-health advice, diagnosis, personality or character scoring, employee evaluation, ranking, automated eligibility, professional care, or an outcome guarantee. Consequential interpretation requires human review.

## License

MIT. See `LICENSE`.
