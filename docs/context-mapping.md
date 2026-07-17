# Condition Mapping — v1.3.0

Catalyst Grit v1.3.0 replaces score-first interpretation with inspectable condition maps.

## Maps

- **Pressure:** overall pressure, competing load, decision ambiguity, dependency friction, and stakeholder friction.
- **Constraints:** type, controllability, control zone, friction layer, severity, and notes.
- **Supports:** active, potential, or unavailable channels with reliability and capacity contribution.
- **Capacity:** energy, clarity, attention, coordination, support access, available time, protected recovery time, and horizon.
- **Control view:** routes conditions into control, influence, outside control, or unknown.
- **Friction layers:** distinguishes immediate, near-term, and structural conditions.

## Interpretation contract

Every generated review flag includes `source_paths` and `input_conditions`. Completeness identifies missing context rather than silently assuming values. Contradictions cite both source paths and provide a human-review prompt. Confidence describes record completeness and internal consistency only; it is not outcome confidence.

The composite conditions score remains available for continuity, but the output declares `component_context_required` and all interfaces show condition maps and component explanations with the score.
