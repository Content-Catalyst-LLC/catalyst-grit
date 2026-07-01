# Export Specification

Catalyst Grit exports are JSON records intended to be reviewable, portable, and easy to archive.

## Required fields

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

Exports should be treated as structured reflection records, not diagnostic data.
