# Repository architecture

Catalyst Grit v1.5.0 uses the recovery-record engine as its only production domain model.

```text
Public WordPress browser demo ─┐
                              ├─ shared parity contract ─ Canonical engine
Python package and CLI ───────┘                         │
                                                        ├─ JSON / Markdown records
Authenticated WordPress workspace ─ private bundle ────┤
SQLite workspace ─ projects, revisions, plans, learning┘
```

## Canonical layers

- `VERSION` is the release identity source.
- `src/catalyst_grit/core.py` owns normalization, condition mapping, recovery planning, retrospectives, pattern candidates, and canonical output generation.
- `src/catalyst_grit/storage.py` owns private projects, append-only revisions and learning history, project pattern aggregation, source-linked system changes, retention, import, and export.
- `src/catalyst_grit/migrations/` contains four ordered, packaged SQLite migrations.
- `schemas/catalyst_grit_record.schema.json` defines portable canonical records.
- `schemas/catalyst_grit_workspace_bundle.schema.json` defines private workspace exports.
- `tests/fixtures/parity_cases.json` verifies Python and JavaScript produce identical outputs.
- `scripts/release_contract.py` guards package, browser, WordPress, migration, persistence, and release integrity.

## Browser boundary

The public WordPress demo remains client-side and non-persistent. Its calculation module is independently executable under Node for Python/browser golden parity. The authenticated workspace stores a private per-user bundle; the complete institutional persistence model remains SQLite-backed.

## Learning boundary

Pattern candidates are generated only from explicit record values and carry source paths. Project aggregation is descriptive, reviewable, and separate from the recovery score. Pattern reviews and system-change events are append-only. No production layer contains trait metrics, personality labels, diagnosis, employee ranking, or automated eligibility logic.

## Legacy boundary

The old Flask event-count and trait-metrics prototype is under `legacy/flask-tracker`. It is not installed, imported by production code, included in the WordPress artifact, or represented by the current OpenAPI contract.
