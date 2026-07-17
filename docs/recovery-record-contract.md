# Recovery Record Contract v1.5.0

The canonical record contains `metadata`, `user_input`, `normalized_input`, `findings`, `human_review`, and `extensions`.

## Input sections

The `learning` section retains the earlier observations, assumptions, and adaptations fields and adds:

- `what_happened`
- `what_was_expected`
- `what_changed`
- `what_helped`
- `what_hindered`
- `what_was_learned`
- `repeat`
- `redesign`
- `uncertainties`
- `pattern_reviews`

Pattern reviews use a stable `pattern_key` and one of `accept`, `reject`, or `correct`. A correction may provide a replacement label and notes.

## Generated findings

`findings` contains methodology, condition maps, interpretation, component scores, state, traceable flags, recommended actions, the executable `recovery_plan`, `retrospective`, `adaptation_patterns`, `learning_loop`, decision note, limits, and calculation provenance.

Every adaptation-pattern candidate includes:

- a stable key and category;
- a plain-language label and basis;
- occurrence count;
- exact source paths and recorded evidence values;
- a proposed adaptation;
- current review decision and correction; and
- an interpretation statement limiting the candidate to recorded conditions.

The learning loop explicitly declares that personality labeling is prohibited. It preserves uncertainty and requires review before inferred patterns are treated as accepted learning.

## Compatibility

Inputs from v1.0.x through v1.4.0 remain importable. Missing v1.5.0 retrospective and pattern-review fields receive visible empty compatibility defaults. Historical submitted values and revisions are never silently rewritten.
