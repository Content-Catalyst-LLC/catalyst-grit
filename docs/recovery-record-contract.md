# Recovery Record Contract v1.2.0

## Layers

| Layer | Purpose |
|---|---|
| `metadata` | Record identity, versions, lifecycle, timestamps, provenance |
| `user_input` | Accepted submitted sections before normalization |
| `normalized_input` | Strict values used by the calculation engine |
| `findings` | Methodology, components, states, flags, actions, limits, provenance |
| `human_review` | Review lifecycle and explicit human override |
| `extensions` | Namespaced additions such as `org.example.field` |

## Required normalized sections

`context`, `trigger`, `impact`, `pressure`, `constraints`, `supports`, `capacity`, `response`, `learning`, and `next_steps` are all required. Unknown fields fail closed. New fields must arrive through a new schema version or a namespaced extension.

## Lifecycle

Record status: `draft`, `active`, `under_review`, `reviewed`, or `archived`.

Human review status: `not_reviewed`, `needs_review`, `in_review`, `reviewed`, or `changes_requested`. A reviewed record requires both reviewer and reviewed timestamp.

## Identity and provenance

Record IDs match `cgr_` plus 32 lowercase hexadecimal characters. Generated records retain source schema version, source channel, creator label, optional source record ID, and notes.

## Migration rule

v1.0.x flat fields are mapped into the nested sections and labeled with migration provenance. The engine never emits a v1.0.x output.
