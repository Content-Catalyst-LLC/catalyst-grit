# Team Recovery and Facilitated Review

Catalyst Grit v1.6.0 adds a private, consent-aware team recovery layer around the existing canonical recovery record. It is designed for facilitated reflection on shared work conditions, not evaluation of individuals.

## Team roles

Each recovery project has explicit memberships with one of five roles:

- **Owner** — manages the project and may grant owner access.
- **Facilitator** — prepares and leads facilitated reviews.
- **Contributor** — submits perspectives and participates in agreements.
- **Reviewer** — reviews shared agreements and evidence.
- **Observer** — receives shared context without managing the process.

Memberships also record status, access scope, and consent state. New projects automatically receive an active owner membership for the project owner.

## Facilitated review lifecycle

A facilitated session records:

1. Purpose, facilitator, date, agenda, and ground rules.
2. Participants, attendance state, consent, and sharing scope.
3. Append-only perspectives linked to the project, session, and optionally a recovery record.
4. Shared agreements with owners, dates, support needs, evidence, and append-only status events.
5. Session status from planned through completed or cancelled.

Default ground rules prohibit ranking, diagnosis, hidden performance evaluation, and character judgments. Participants control whether a contribution is shared, facilitator-only, or private.

## Perspective visibility

- **Shared** perspectives are visible to active project members.
- **Facilitator-only** perspectives are visible to the contributor and project owners/facilitators.
- **Private** perspectives are visible only to the contributor.
- Withdrawn perspectives are excluded from normal views.

Perspectives are append-only. Corrections should be recorded as a new perspective rather than rewriting prior evidence.

## Agreements

Facilitated agreements use the statuses `proposed`, `accepted`, `in_progress`, `completed`, `blocked`, and `retired`.

- Completion requires evidence.
- Blocking requires a recorded support need.
- Every transition creates an append-only event.

## Interpretation boundary

Team summaries aggregate counts of shared perspectives and agreement states. They never calculate an individual score, rank participants, infer personality traits, diagnose health, or create hidden performance records.
