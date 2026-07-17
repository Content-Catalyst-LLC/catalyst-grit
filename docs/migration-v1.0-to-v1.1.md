# Migration from v1.0.x to v1.2.0

The engine detects a flat request containing `challenge` and no `input` object.

- `challenge` becomes context title and trigger summary.
- `domain` becomes context domain.
- impact, pressure, energy, support, and clarity scales move into their canonical sections.
- recovery actions become response actions.
- time horizon moves into capacity.
- review status maps into record and human-review lifecycle fields.
- provenance records source `migration` and source schema `1.0.1`.

Use:

```bash
grit migrate examples/grit_record_v1_0_input.json --output migrated.json
grit generate migrated.json --output record.json
```

Record IDs and timestamps are generated when the legacy request does not provide them.
