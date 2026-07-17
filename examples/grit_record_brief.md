# Catalyst Grit Recovery Brief

## Record

- **Record ID:** cgr_11111111111111111111111111111111
- **Status:** draft
- **Created:** 2026-07-17T12:00:00Z
- **Updated:** 2026-07-17T12:00:00Z
- **Domain:** project

## Context

### Sustainability reporting project recovery

The workstream lost momentum after conflicting stakeholder feedback and a missed internal checkpoint.

## Condition maps

### Pressure map

- **Overall pressure:** 8.0/10 — `$.input.pressure.level`
- **Decision ambiguity:** 7.0/10 — `$.input.pressure.decision_ambiguity`
- **Dependency friction:** 8.0/10 — `$.input.pressure.dependency_friction`
- **Stakeholder friction:** 7.0/10 — `$.input.pressure.stakeholder_friction`
- **Competing load:** 8.0/10 — `$.input.capacity.load_level`

### Constraint map

- **Final approval dependency:** influence · near term · 8.0/10
- **Limited review window:** outside control · immediate · 7.0/10

### Support map

- **Project lead:** active · reliability 8.0/10 · contribution 8.0/10
- **Decision log:** active · reliability 7.0/10 · contribution 6.0/10

### Completeness and review

- **Completeness:** 100.0%
- **Confidence:** high (100.0/100)

#### Missing-context prompts

- No required context prompts remain.

#### Contradictions

- No contradictions detected.

## Recovery conditions

- **Score (component context required):** 47.8/100
- **Generated state:** fragile recovery conditions
- **Effective state:** fragile recovery conditions
- **Methodology:** cg-recovery-conditions v1.6.0

## Component scores

- **Impact Buffer:** 5.0/15.0 — Lower recorded impact leaves more near-term recovery room; severity remains visible separately.
- **Pressure Buffer:** 3.3/15.0 — Lower recorded pressure increases the room available for deliberate recovery action.
- **Energy Capacity:** 6.7/15.0 — Recorded energy is treated as available capacity, not motivation or character.
- **Support Capacity:** 8.3/15.0 — Recorded access to support increases recovery capacity.
- **Clarity Capacity:** 5.0/15.0 — Recorded clarity supports prioritization and a bounded next step.
- **Action Readiness:** 15.0/15.0 — Readiness increases with up to four distinct response or next-step actions.
- **Constraint Manageability:** 4.5/10.0 — Manageability reflects the recorded controllability of constraints; no listed constraints defaults to full manageability.

## Review flags

- **High · pressure:** Clarify what can pause, wait, or be delegated.
- **High · constraints:** Route the dependency to an owner or escalation path.

## Recommended actions

- **High:** Document unresolved assumptions — Preserved from the recorded response or next-step plan.
- **Medium:** Schedule a short stakeholder review — Preserved from the recorded response or next-step plan.
- **Medium:** Clarify the next decision owner — Preserved from the recorded response or next-step plan.
- **Medium:** Break the work into a 48-hour recovery task — Preserved from the recorded response or next-step plan.
- **High:** Write a one-sentence definition of recovery for this situation. — Clarity is at or below the midpoint.
- **High:** Reduce the work to one near-term checkpoint instead of a full reset. — Pressure is elevated.

## Learning loop

- **What happened:** Conflicting review channels changed the deliverable after the checkpoint.
- **What was expected:** One decision owner would consolidate feedback before review.
- **What changed:** Feedback arrived through separate channels and the decision owner was not explicit.
- **Retrospective completion:** 100.0%

### Repeat

- Use a single shared decision log.
- Reducing scope to one decision
- Using a shared decision log

### Redesign

- Require one named decision owner before the review window opens.
- Record the decision owner before the next review cycle.

### Uncertainty

- Whether all reviewers can use the same feedback channel.

### Adaptation pattern candidates

- **Recurring Pressure:** publication deadline — inferred · evidence `$.input.pressure.sources[0]`
- **Recurring Pressure:** stakeholder disagreement — inferred · evidence `$.input.pressure.sources[1]`
- **Scope Workload:** parallel publication work — inferred · evidence `$.input.pressure.competing_demands[0]`
- **Scope Workload:** reviewer availability — inferred · evidence `$.input.pressure.competing_demands[1]`
- **Dependency Failure:** Final approval dependency — inferred · evidence `$.input.constraints.items[0]`
- **Clarity Failure:** Decision or recovery clarity gap — inferred · evidence `$.input.capacity.clarity_level`
- **Scope Workload:** High competing load — inferred · evidence `$.input.capacity.load_level`
- **Recovery Action Helped:** Reducing scope to one decision — inferred · evidence `$.input.learning.what_helped[0]`
- **Recovery Action Helped:** Using a shared decision log — inferred · evidence `$.input.learning.what_helped[1]`
- **Action Did Not Help:** Parallel feedback channels — inferred · evidence `$.input.learning.what_hindered[0]`
- **Action Did Not Help:** Unclear approval ownership — inferred · evidence `$.input.learning.what_hindered[1]`
- **Adaptation Candidate:** Require one named decision owner before the review window opens. — inferred · evidence `$.input.learning.redesign[0]`
- **Adaptation Candidate:** Record the decision owner before the next review cycle. — inferred · evidence `$.input.learning.redesign[1]`

## Decision note

Recorded recovery conditions are assessed as fragile recovery conditions. The composite conditions score is 47.8/100 and must be interpreted with the pressure, constraint, support, capacity, and component maps. Protect available capacity, address the highest-friction condition, and update the record at the next checkpoint.

## Human review

- **Review status:** not_reviewed
- **Reviewer:** Not assigned
- **Override applied:** No

## Interpretation limits

- Describes recorded recovery conditions, not a person's character.
- Does not diagnose mental health, predict outcomes, or replace professional support.
- Must not be used for employee ranking, automated eligibility, or performance evaluation.
- Generated findings require human review when used for consequential decisions.

## Release provenance

- **Schema version:** 1.6.0
- **Engine version:** 1.6.0
- **Method path:** context → trigger → impact → pressure → constraints → supports → capacity → response → learning → retrospective → adaptation patterns → next steps → human review
