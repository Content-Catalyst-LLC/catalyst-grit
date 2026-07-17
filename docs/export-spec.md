# Export Specification

Catalyst Grit v1.5.0 exports canonical JSON validated by `schemas/catalyst_grit_record.schema.json`, an optional Markdown review brief, and private `catalyst-grit-workspace/1.0` bundles.

Canonical-record exports preserve record identity, source provenance, submitted input, normalized values, methodology profile, component explanations, condition maps, recovery plan, generated retrospective, source-linked adaptation patterns, uncertainty, human review, and namespaced extensions.

Record workspace exports additionally preserve revisions, actions, action events, blockers, reassessments, retrospectives, checkpoints, reviews, status history, and audit events.

Project workspace exports additionally preserve aggregated patterns, append-only pattern reviews, source-linked system-change proposals, evidence notes, pilot decisions, and immutable system-change events. Project import restores canonical record revisions and, where present, reviewed patterns and system-change records while creating a traceable import event rather than rewriting source history.

JSON exports are portable reflection and project-learning records. They are not diagnostic records, employee ratings, personality profiles, or predictions.
