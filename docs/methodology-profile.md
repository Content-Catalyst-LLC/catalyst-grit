# Methodology Profile v1.7.0

The default profile is stored at `methodology/recovery-profile-v1.7.0.json` and identified as `cg-recovery-conditions@1.7.0`.

The weighted recovery-condition calculation remains unchanged for longitudinal compatibility. v1.7.0 adds a traceability layer in the private workspace; evidence strength, assumption confidence, and handoff validation do not alter the recovery score.

## Evidence method

The workspace records evidence exactly as supplied, assigns a content hash to the immutable source snapshot, and preserves source product, source version, URI or artifact ID, provenance chain, strength, review state, and append-only events. Evidence may support, challenge, contextualize, derive from, or conflict with another artifact. A conflict is surfaced for review rather than automatically resolved.

## Assumption method

Assumptions remain explicit statements with uncertainty, a user-supplied confidence value, an owner, review date, source paths, and active, validated, rejected, or retired state. Confidence is a statement-support indicator, not a probability forecast, performance score, or measure of a person.

## Handoff method

Cross-product handoffs preserve stable artifact IDs, source and target products, source version, provenance, snapshot or live-reference mode, payload content hash, and valid, invalid, stale, or conflict state. Validation events are append-only. Live references require a URI and remain visible when stale.

## Decision handoff method

The Decision Studio packet combines only recorded recovery context, condition maps, actions, evidence, assumptions, and human-review state. It preserves unresolved assumptions and conflicting evidence and prohibits conversion into individual ranking, diagnosis, eligibility, or hidden evaluation.
