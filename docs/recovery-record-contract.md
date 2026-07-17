# Recovery Record Contract v1.7.0

The canonical recovery record continues to contain `metadata`, `user_input`, `normalized_input`, `findings`, `human_review`, and `extensions`. The v1.7.0 evidence, assumption, and handoff ledgers are private workspace entities linked to the canonical record and revision IDs rather than silently embedded into or rewriting historical records.

## Canonical findings

`findings` retains methodology, condition maps, interpretation, component explanations, state, traceable flags, recommended actions, executable recovery plan, retrospective, adaptation patterns, learning loop, decision note, limits, and calculation provenance.

## Linked evidence

Workspace evidence preserves a stable ID, type, title, content, source location, source artifact, source product and version, provenance chain, strength, review state, content hash, and append-only events. Links identify whether evidence supports, challenges, contextualizes, derives from, or conflicts with a record, revision, assumption, action, checkpoint, system change, facilitated agreement, or handoff.

## Explicit assumptions

Workspace assumptions preserve statement, uncertainty, confidence, owner, review date, source paths, lifecycle state, evidence links, and append-only events. They are never silently promoted to facts.

## Product handoffs

Workspace handoffs preserve stable artifact identity, source and target product, source version, artifact type, direction, snapshot or live-reference mode, source URI, payload, content hash, provenance, validation state, stale date, conflict notes, and append-only events.

## Compatibility

Canonical records from v1.0.x through v1.6.0 remain importable. Migration 006 adds linked workspace tables without rewriting canonical records, revisions, plans, learning loops, team perspectives, or facilitated agreements.
