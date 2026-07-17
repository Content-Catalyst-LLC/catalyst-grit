# Evidence, Assumptions, and Decision Handoffs

Catalyst Grit v1.7.0 adds a private traceability layer around recovery records. It preserves what was observed, what remains assumed, where an artifact came from, how it was reviewed, and what was handed to another Sustainable Catalyst product.

## Evidence ledger

Evidence items may be notes, source links, file references, quotes, observations, datasets, calculations, analyses, experiment results, methods, or published reference documents. Every item preserves a stable ID, content hash, source product and version, source URI or artifact ID, provenance chain, strength, review state, and append-only review events.

Evidence can support, challenge, contextualize, derive from, or conflict with a record, revision, assumption, action, checkpoint, system change, facilitated agreement, or handoff. Conflicts remain visible rather than being silently resolved.

## Assumption register

Assumptions are explicit statements with uncertainty, confidence, an owner, a review date, source paths, and active, validated, rejected, or retired states. Lifecycle events are append-only. Confidence expresses the user's current support for the statement; it is not a probability forecast or a score for a person.

## Product handoffs

The handoff contract supports Catalyst Canvas, Catalyst Data, Workbench, Sustainable Catalyst Lab, Decision Studio, Knowledge Library, Research Librarian, Catalyst Grit, and explicitly identified external sources.

Each handoff preserves:

- a stable handoff and source artifact ID;
- source and target product names;
- source product version;
- artifact type;
- inbound or outbound direction;
- read-only snapshot or live-reference mode;
- source URI where applicable;
- payload content hash;
- provenance chain;
- valid, invalid, stale, or conflict state; and
- append-only validation events.

Live references require a URI. Supplied payloads can be compared with the recorded content hash to identify conflicts. Stale references remain available with a visible state.

## Decision Studio packet

`decision-handoff` creates `sustainable-catalyst-decision-handoff/1.0`. The packet includes the recovery context, condition map, interpretation, recovery plan, actions, evidence, assumptions, human-review state, review history, canonical record hash, and explicit decision guardrails. Creating the packet also records an outbound handoff artifact in the workspace.

## Safety boundary

Evidence and handoffs improve traceability. They do not turn recovery records into employee ratings, personality profiles, diagnoses, eligibility determinations, or automated predictions.
