# Learning Loops and Adaptation Patterns

Catalyst Grit v1.5.0 turns completed or reassessed recovery work into reviewable learning without converting a setback into a judgment about a person.

## Retrospectives

A retrospective records the event, the prior expectation, what changed, helpful and hindering conditions, learning, practices to repeat, elements to redesign, and unresolved uncertainty. The engine reports completion and source paths, but it does not fill gaps with generated claims.

Each saved canonical revision receives its own append-only retrospective row. Reassessing a record creates a new revision and a new retrospective rather than editing the prior account.

## Adaptation-pattern candidates

The engine may identify candidates in these categories:

- recurring pressure;
- dependency failure;
- support gap;
- clarity failure;
- scope or workload friction;
- a recovery action that helped;
- an action that did not help; and
- a user-authored adaptation candidate.

A candidate contains its basis, evidence values, and exact source paths. The initial state is `inferred`. A user may accept it, reject it, or correct its label. Rejected candidates remain in history so the system does not silently reassert them as accepted knowledge.

## Project pattern library

The private SQLite workspace can aggregate matching candidates across the current revisions of records in a project. Aggregated evidence includes the contributing record, revision, source path, and value. The minimum occurrence threshold is configurable; singleton candidates can be shown explicitly for review.

Aggregation is descriptive. It does not infer motivation, disposition, resilience, grit, or employability.

## System changes

A reviewed pattern can motivate a source-linked system-change proposal. Each proposal includes:

- title and proposed process or system change;
- owner;
- source recovery records and evidence note;
- expected benefit;
- pilot start and end dates;
- review result; and
- decision history: proposed, piloting, adopt, revise, defer, or retire.

System-change events are append-only. Exported projects preserve the proposal, sources, evidence, pilot decisions, and history.
