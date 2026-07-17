# Export Specification

Catalyst Grit v1.0.1 exports are JSON records intended to be reviewable, portable, and easy to archive. The canonical schema is `schemas/catalyst_grit_record.schema.json`.

## Required input fields

- `challenge`
- `domain`
- `impact_severity`
- `pressure_level`
- `energy_level`
- `support_level`
- `clarity_level`
- `recovery_actions`
- `time_horizon_days`
- `review_status`

## Generated fields

- `recovery_score`
- `resilience_state`
- `risk_flags`
- `next_actions`
- `decision_note`
- `method_path`
- `schema_version`
- `engine_version`

Generated records must preserve the exact normalized inputs alongside findings and release provenance. Exports are structured reflection records, not diagnostic data, employee ratings, or predictions of future performance.
