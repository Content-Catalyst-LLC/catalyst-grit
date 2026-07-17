# Catalyst Grit

**Current release: v1.3.0 — Pressure, Constraint, Support, and Capacity Mapping**

Catalyst Grit is a private-by-default human-systems recovery and learning engine. It documents setbacks, the conditions shaping recovery, actions, checkpoints, and learning without scoring character, diagnosing health, or ranking people.

## v1.3.0 capabilities

- Pressure map covering overall pressure, competing load, decision ambiguity, dependency friction, and stakeholder friction
- Constraint map with type, severity, control zone, and immediate / near-term / structural layer
- Support map with availability status, reliability, and capacity contribution
- Recovery-capacity profile for energy, clarity, attention, coordination, time, and support access
- Control / influence / outside-control routing view
- Completeness prompts, contradiction detection, and confidence indicators
- Review flags that cite the exact input paths and values that caused them
- Composite score displayed only with component and condition context
- Persistent SQLite projects, append-only revisions, checkpoints, reviews, audit history, retention, import, and export
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
```

Catalyst Grit is educational and analytical infrastructure. It is not diagnosis, mental-health advice, employee evaluation, automated eligibility, or an outcome guarantee.
