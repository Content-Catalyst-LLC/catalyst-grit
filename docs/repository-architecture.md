# Repository Architecture

Catalyst Grit v2.0.0 uses the recovery-record engine as its only production domain model.

```text
Public WordPress demo ───────────────┐
Python package and CLI ──────────────┼─ Canonical recovery engine
Authenticated WordPress workspace ──┤             │
SQLite institutional workspace ─────┤             ├─ governed publications
Institutional API adapter ───────────┤             ├─ portable bundles
Publication service ─────────────────┘             └─ cross-product handoffs
```

## Canonical layers

- `VERSION` is the release identity source.
- `src/catalyst_grit/core.py` owns normalization and generated recovery findings.
- `src/catalyst_grit/storage.py` owns private persistence, revisions, plans, learning, team review, evidence, handoffs, monitoring, policies, access reviews, API clients, publication metadata, methodology governance, schema deprecation, and audits.
- `src/catalyst_grit/publication.py` owns redaction-aware reports and deterministic multi-format exports.
- `src/catalyst_grit/api.py` owns the framework-neutral authenticated institutional route contract.
- `src/catalyst_grit/migrations/` contains eight ordered, packaged SQLite migrations.
- `schemas/` defines canonical records, private bundles, publications, and API responses.
- `openapi.yaml` mirrors the production institutional routes and required scopes.
- `scripts/release_contract.py` guards package, browser, WordPress, migration, persistence, publication, API, and release integrity.

## Security and traceability boundary

Opaque API tokens are returned once and stored only as SHA-256 hashes. Authorization combines explicit scopes and optional project allowlists. API requests, access reviews, and publication lifecycle events are append-only. Redaction creates a new governed artifact and never mutates the private source record.

The public WordPress demo remains non-persistent. The authenticated WordPress workspace remains per-user and private. Institutional persistence and API authorization remain in the Python/SQLite service layer.
