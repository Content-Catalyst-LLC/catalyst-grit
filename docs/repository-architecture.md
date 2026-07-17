# Repository architecture

Catalyst Grit v1.8.0 uses the recovery-record engine as its only production domain model.

```text
Public WordPress browser demo ─┐
                              ├─ shared parity contract ─ Canonical engine
Python package and CLI ───────┘                         │
                                                        ├─ JSON / Markdown records
Authenticated WordPress workspace ─ private bundle ────┤
SQLite workspace ─ records, plans, teams, evidence ─────┤
Cross-product handoff contract ─────────────────────────┘
```

## Canonical layers

- `VERSION` is the release identity source.
- `src/catalyst_grit/core.py` owns canonical normalization and generated recovery findings.
- `src/catalyst_grit/storage.py` owns private projects, revisions, plans, learning history, team facilitation, evidence, assumptions, handoffs, retention, import, and export.
- `src/catalyst_grit/migrations/` contains six ordered, packaged SQLite migrations.
- `schemas/` defines canonical records and portable private workspace bundles.
- `tests/fixtures/parity_cases.json` verifies Python and JavaScript canonical-output parity.
- `scripts/release_contract.py` guards package, browser, WordPress, migration, persistence, and release integrity.

## Traceability boundary

Evidence and handoff content is hashed and source-linked. Review, assumption, and handoff lifecycle events are append-only. A stale or conflicting source is retained with a visible state. Traceability does not authorize diagnosis, personality inference, employee ranking, automated eligibility, or hidden evaluation.

## Browser boundary

The public WordPress demo remains client-side and non-persistent. The authenticated workspace stores a private per-user bundle. The complete persistence and handoff service remains SQLite-backed.

## Legacy boundary

The old Flask event-count and trait-metrics prototype is under `legacy/flask-tracker`. It is not installed, imported by production code, included in the WordPress artifact, or represented by the current OpenAPI contract.
