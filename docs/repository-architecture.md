# Repository architecture

Catalyst Grit v1.3.0 uses the recovery-record engine as its only production domain model.

```text
WordPress browser demo
        ↓ parity fixtures
Canonical recovery-record contract
        ↓
Python package engine and CLI
        ↓
JSON / Markdown exports and future API integrations
```

## Canonical layers

- `VERSION` is the release identity source.
- `src/catalyst_grit/core.py` owns normalization, scoring, states, flags, next actions, and output generation.
- `schemas/catalyst_grit_record.schema.json` defines portable records.
- `tests/fixtures/parity_cases.json` verifies Python and JavaScript produce identical outputs.
- `scripts/release_contract.py` guards repository and release integrity.

## Browser boundary

The WordPress demo remains client-side and non-persistent. Its calculation module is independently executable under Node so release validation can compare it with the Python engine.

## Legacy boundary

The old Flask event-count and trait-metrics prototype is under `legacy/flask-tracker`. It is not installed, imported by production code, included in the WordPress artifact, or represented by the current OpenAPI contract.
